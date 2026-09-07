# PROMPTS.md — Prompts sent to Claude Code

All prompts below are the exact prompts I sent to Claude Code, in order, grouped by task.

---

## Task 0: Project Setup and Connection

Initialize a uv project named lead-desk with dependencies 'agents', 'openai', and 'python-dotenv'. Create a .env file containing GEMINI_API_KEY=your_key_here and ensure .env is listed in .gitignore. Write main.py with an async entrypoint using asyncio.run(). Use the Agents SDK (via OpenAI compatibility layer or OpenAIChatCompletionsModel configured for Gemini's OpenAI-compatible endpoint base URL) with gemini-2.5-flash. Load the key with python-dotenv, run a hardcoded client message asynchronously using Runner.run(), and print the response.

---

## Task 1: Sample Data and Lookup Tools

Create leads.json containing six client messages with fields (id, message, platform) covering a well-budgeted request, a revenue-share offer, a vague job, an urgent request, a small job, and an aggressive deadline scenario. In main.py, define two Python tools decorated for the agent: lookup_rate_card(skill: str) and check_availability(week: str). Give both tools clear docstrings so the agent knows when to invoke them, and configure the agent to call lookup_rate_card before discussing money or state that a skill is unknown if not listed.

---

## Task 2: Context and Data Privacy

Define a Dataclass or Pydantic class named FreelancerProfile with fields: name, min_rate_pkr_hour, skills (dict/list), hours_free_per_week, and verified (bool). Pass an instance of FreelancerProfile into Runner.run() as context. Update lookup_rate_card and check_availability to take RunContext[FreelancerProfile] as their first argument and read rate card/availability directly from ctx.context rather than global variables. Ensure min_rate_pkr_hour is never included in system instructions or prompts. Print the JSON schema of lookup_rate_card to verify context is hidden from the model.

---

## Task 3: Structured Output and Code-Based Saving

Define a LeadTriage Pydantic model with fields: intent (str), budget_pkr (Optional[int]), red_flags (list[str]), priority (Literal['high', 'medium', 'low']), and suggested_reply (str). Set response_format=LeadTriage on the Agent so output is typed. Add a save_lead function that appends a lead to saved.json. In Python (outside the LLM prompt), inspect the returned LeadTriage object; if output.priority == 'high', print a one-line summary with priority and budget_pkr, then call save_lead. Ensure revenue-share messages populate red_flags.

---

## Task 4: Zero-LLM Guardrail

Write a deterministic Python function check_input_guardrail(message: str) -> bool that runs before calling Runner.run(). Use rule-based pattern/keyword checking to detect requests asking to lie, overstate, or fabricate work experience (e.g., claiming unearned years of experience). If triggered, print a polite refusal directly and exit the process cleanly with status 0 without invoking the Gemini API or making any model calls.

---

## Task 5: Option B — Conditional Tools

Implement Bonus Option B by modifying the agent setup before Runner.run(). Check profile.verified: if verified is True, include send_proposal in the agent's tools list; if False, exclude send_proposal completely from the agent definition. Add a test run showing execution when verified=False (where the tool schema is omitted) and when verified=True.
