# Constitution — Code Review Desk

Rules this build may not break.

## Provider & Configuration

- **Provider**: OpenAI
- **API Key**: `OPENAI_API_KEY` loaded from `.env` only
- **Model**: `gpt-4o-mini` configured directly on each agent instance
- **No global default client**: every agent carries its own model configuration

## Core Invariants

1. **Secrets live in `.env` only**
   - `.env` is gitignored
   - No secret value ever appears in a report, log, trace, or streamed output
   - Output guardrails reject any finding that quotes a secret found in the diff

2. **No tool raises into the runner**
   - Every tool wraps its body in error handling
   - Failures return a model-usable error message object
   - The Runner never receives an unhandled exception from a tool

3. **Review reproducibility from the diff alone**
   - Given the same diff input and ReviewContext, the Desk produces the same structured findings
   - No hidden state, no ambient filesystem reads during review
   - The ReviewContext (repo, language, ruleset_id, strictness) is the only external input besides the diff

4. **Specification-first**
   - No `.py` file exists until `constitution.md`, `spec.md`, `plan.md`, and `tasks.md` are committed
   - Git history is the evidence

5. **ReviewContext never leaks into prompts**
   - `ReviewContext` fields are read by tools through a wrapper
   - Prompt text contains no repository name
   - Generated tool schemas contain no wrapper parameters
