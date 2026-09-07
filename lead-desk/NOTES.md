# NOTES.md — What went wrong and what I changed

**Task 0 — Project and connection**
First attempt had synchronous code with `agent.run()`. The SDK requires `Runner.run()` inside an async function. Changed `main()` to `async def main()` and wrapped the call with `asyncio.run()`.

**Task 1 — Sample data and lookup tools**
Initial tool docstrings were too terse — the model was not calling `lookup_rate_card` before quoting prices. Added an explicit instruction in the docstring ("Call this tool BEFORE discussing pricing") and a matching rule in the system prompt. After that the model called the tool reliably.

**Task 2 — Data the model is never given**
First version stored `min_rate_pkr_hour` as a module-level constant and referenced it inside the tool function directly. The printed schema included a `min_rate` parameter the model could read. Refactored so the rate lives only in the `FreelancerProfile` instance passed as `context`, and the tool reads it through `ctx.context`. The schema no longer exposes the field.

**Task 3 — A verdict the program can act on**
The first implementation let the agent call a `save_lead` tool directly — the save decision was inside the prompt, not the code. Replaced it with a plain Python function and moved the `if triage.priority == "high"` check into `main()`. Also fixed `budget_pkr` which was initially returned as a string; changed the type to `Optional[int]` so arithmetic works.

**Task 4 — Refusing before you pay**
First guardrail used a simple substring match on "lie" and "fake", which missed phrases like "say you have 10 years experience". Added regex patterns for common fabrication phrasings and a separate credential-keyword check to avoid false positives on ordinary messages.

**Task 5 — Bonus: Conditional tools**
Initial draft always registered `send_proposal` in the tools list regardless of the `verified` flag. Added a conditional append inside `build_agent()` and a matching instruction block so the model only sees the tool when the profile is verified.
