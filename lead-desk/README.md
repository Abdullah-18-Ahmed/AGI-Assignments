# Lead Desk

An AI agent that triages inbound freelance client messages. It reads one raw client message, works out what the client actually wants, checks it against your rate card and availability, and returns a structured, typed verdict your program can branch on.

Built as a practical assessment project — see `PROMPTS.md` and `NOTES.md` for the prompts used and the development log.

## Features

- **Intent classification** — recognises well-budgeted requests, revenue-share offers, vague jobs, urgent work, tiny jobs, and aggressive deadlines.
- **Structured output** — returns a typed `LeadTriage` object (intent, budget, red flags, priority, suggested reply), not prose.
- **Private data kept private** — your minimum rate, skills, and free hours live in a `FreelancerProfile` passed as hidden context. The model reads them only through tools and can never reveal your lowest acceptable rate.
- **Code-driven decisions** — the guardrail, the tool set, and the save/no-save choice are all taken by Python, not by prompting the model.
- **Zero-LLM input guardrail** — messages asking you to misrepresent or fabricate experience are rejected instantly with no API call, no perceptible pause, clean exit.
- **Conditional tools (Bonus B)** — `send_proposal` only exists when the profile is `verified`.

## Requirements

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- An API key (see below)

## Setup

```bash
# 1. Create the virtual environment and install dependencies
uv sync

# 2. Create your .env file
#    Copy the example and fill in your key
cp .env.example .env   # Windows: copy .env.example .env
```

`.env` should contain:

```
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4o
```

`.env` is git-ignored — never commit your key.

## Usage

Run the agent against every message in `leads.json`:

```bash
uv run python main.py
```

For each lead the program:
1. Prints the tool JSON schemas (evidence that hidden context is not exposed).
2. Applies the input guardrail — a blocked message prints a polite decline and exits.
3. Runs the agent and prints the typed triage verdict.
4. Saves the lead to `saved.json` only when `priority == "high"`.

Run the Bonus B verification (conditional `send_proposal` tool):

```bash
uv run python test_bonus_b.py
```

## Project layout

```
lead-desk/
├── main.py           # Agent, tools, guardrail, and the async orchestration loop
├── leads.json        # Six sample client messages of varying quality
├── saved.json        # Leads saved by the program (high priority only)
├── proposals.json    # Written by the conditional send_proposal tool
├── test_bonus_b.py   # Bonus B: verified vs unverified tool-set comparison
├── PROMPTS.md        # The exact prompts sent to Claude Code, grouped by task
├── NOTES.md          # Development log: what went wrong first time, what changed
├── pyproject.toml    # uv project definition
└── .env.example      # Template for the git-ignored .env
```

## How it works

```
Client message
      │
      ▼
╔═════════════════════════════════╗
║ Input guardrail (pure Python,   ║  ← rejects fabrication requests,
║ no API call)                    ║    zero cost, instant
╚═════════════════════════════════╝
      │ (passes)
      ▼
Agent: Runner.run(agent, message, context=profile)
  • lookup_rate_card(skill)    ← reads rate from hidden context
  • check_availability(week)   ← reads free hours from hidden context
  • returns a LeadTriage (typed) object
      │
      ▼
Python code branches:
  if triage.priority == "high" → print banner + save_lead
  else                         → skip
```

### Privacy boundary

`FreelancerProfile.min_rate_pkr_hour` and the skill/hour maps are only reachable through tool results. They never appear in the system prompt or any message sent to the model. The printed tool JSON schema confirms the context parameter is stripped before the model sees it.

### Where decisions live

| Concern | Location |
|---|---|
| Private data | `FreelancerProfile` as hidden `context` |
| Input guardrail (no API) | `check_input_guardrail()` in `main.py` |
| Tool availability | `build_agent()` conditional append |
| Save / no-save decision | `main()` `if triage.priority == "high"` |
| Retry resilience | `run_with_retry()` exponential backoff |

## Bonus: Task 5 Option B — Conditional tools

`send_proposal` is registered only when `FreelancerProfile.verified` is `True`. `test_bonus_b.py` runs the same lead twice:

- `verified = False` → `send_proposal` is absent from the model's tool list; the model is never offered it.
- `verified = True` → `send_proposal` is present, and a proposal is recorded to `proposals.json`.

## License

All rights reserved. This project was built for a course assessment and is not licensed for reuse.
