---
name: openai-agents-builder
description: Use when building Python agentic applications with the OpenAI Agents SDK - Agent/Runner pipelines, output_type=list[Finding], dynamic system prompts, agent cloning, as_tool/handoff patterns, Guardrails, lifecycle hooks, token tracking, ledger.jsonl, OpenTelemetry, or Chainlit integration.
---

# OpenAI Agents Builder Skill

Expert guidance for building Python agentic pipelines with the OpenAI Agents SDK (`agents-sdk`).

## Core Implementation Patterns

### Agent Definition and Runner
```python
from agents import Agent, Runner

agent = Agent(
    name="SecurityReviewer",
    instructions=dynamic_system_prompt,
    output_type=list[Finding],
)
result = Runner.run(agent, input=diff_text)
```

### Dynamic System Prompts & Context Injection
- Build `instructions` at call time from `ReviewContext` fields
- Never place repository name or secrets in prompt text
- Inject context via tool parameters, not prompt strings

### Agent Cloning
```python
strict_agent = base_agent.clone(
    name="StrictReviewer",
    instructions=strict_instructions,
)
```

### Output Types
- Use `output_type=list[Finding]` for structured findings
- Define `Finding` as a dataclass/pydantic model with: file, line, severity, rule, message

## Multi-Agent Wiring

### Agent-as-a-Tool (Merge agent)
```python
merge_tool = merge_agent.as_tool(
    tool_name="merge_findings",
    tool_description="Merge reviewer findings into one report",
)
```

### Handoff (Remediation agent)
```python
reviewer = Agent(
    name="SecurityReviewer",
    handoffs=["RemediationAgent"],  # conversational transfer on critical finding
)
```

## Execution Controls

### Output Guardrails
```python
from agents import Guardrail

guardrail = Guardrail(
    name="secret_scanner",
    validate=lambda output: not contains_secret(output),
)
agent = Agent(..., output_guardrails=[guardrail])
```

### Error-Handling Tool Wrappers
- Wrap all tools so they return error objects, never raise into the Runner

### Turn Ceilings
- Set `max_turns` on `Runner.run()` to cap conversation depth

### Run-Level Model Overrides
```python
Runner.run(agent, input=..., model="gpt-4o")  # override per-run
```

## Integration

### Lifecycle Hooks
- Register hooks for `on_start`, `on_tool_call`, `on_end` for observability

### Token Tracking
- Capture `result.usage` after each run; aggregate into `ledger.jsonl`

### Custom Runners for ledger.jsonl
- Append one JSON line per run: timestamp, agent, tokens_in, tokens_out, findings_count

### OpenTelemetry Tracing
- Wrap Runner calls with spans; export via OTLP

### Chainlit Interface
- Stream findings as they land (not batched at end)
- Display per-reviewer status indicators
- Show trace with slowest reviewer highlighted
