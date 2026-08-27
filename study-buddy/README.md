# Study Buddy - AI Tutor CLI

A personalized quiz tutor using the OpenAI Agents SDK with three teaching modes (Balanced, Gentle, Strict). Tracks your progress across sessions and focuses on weak topics.

## Setup

1. **Install dependencies** (uses `uv`):
   ```bash
   uv sync
   ```

2. **Add API keys to `.env`**:
   ```env
   GEMINI_API_KEY=your-gemini-key
   OPENAI_API_KEY=your-openai-key  # optional, for tracing
   ```
   - Get Gemini key at https://ai.google.dev/
   - Get OpenAI key at https://platform.openai.com/api-keys (for tracing at platform.openai.com/traces)

3. **Run**:
   ```bash
   python main.py
   ```

## Example Run

```
$ python main.py
Welcome back, Alex!
Name [Alex]: 
Level (beginner/intermediate/advanced) [intermediate]: 

Choose tutor mode:
  1. Balanced (default)
  2. Gentle
  3. Strict
> 2

Starting session with Study Buddy (Gentle). Type 'q' anytime to quit.

Available topics:
  1. Introduction to OpenAI Agents SDK (ID: 1) (0% acc)
  2. Agent Architecture and Components (ID: 2) ⚠ (33% acc)
  3. Creating and Running Your First Agent (ID: 3)
  4. Function Tools and Tool Calling (ID: 4)
  5. Agent Handoffs and Multi-Agent Systems (ID: 5)
  6. Guardrails for Safety and Validation (ID: 6)

Weak topics: Agent Architecture and Components
Press Enter to let tutor pick a weak topic, or enter topic number/ID:
> 

--- Topic: Agent Architecture and Components ---
Q: In the OpenAI Agents SDK, what three core components define an agent's behavior and capabilities?

Your answer: Instructions, tools, and model

Verdict: correct
Feedback: The answer correctly identifies all three core components.

Available topics:
  1. Introduction to OpenAI Agents SDK (ID: 1) (0% acc)
  2. Agent Architecture and Components (ID: 2) (50% acc)
  3. Creating and Running Your First Agent (ID: 3)
  4. Function Tools and Tool Calling (ID: 4)
  5. Agent Handoffs and Multi-Agent Systems (ID: 5)
  6. Guardrails for Safety and Validation (ID: 6)

Weak topics: Agent Architecture and Components
Press Enter to let tutor pick a weak topic, or enter topic number/ID:
> q

==================================================
SESSION SUMMARY
==================================================
  Agent Architecture and Components: 2/3 (67%)
  Introduction to OpenAI Agents SDK: 1/2 (50%)

Overall: 3/5 (60%)
Weak topics: Agent Architecture and Components
==================================================

Progress saved to student_profile.json
```

## What the Agent Does Badly

| Issue | Description |
|-------|-------------|
| **Hallucinated questions** | The `question_writer` (temp 0.9) sometimes invents facts not in `topics.json`, asking about APIs or concepts never covered. |
| **Inconsistent grading** | The `grader` (temp 0.1) still varies on borderline answers — "partial" vs "correct" flips on re-grading identical input. |
| **No pedagogical sequencing** | Topic order is random; it doesn't scaffold from prerequisites to advanced (e.g., asks about handoffs before tools). |
| **Weak topic logic is crude** | A single wrong answer adds a topic to `weak_topics` forever; no decay or mastery threshold to remove it. |
| **No answer normalization** | "LLM" vs "large language model" graded differently; no fuzzy matching or canonicalization. |
| **Single-question cycles** | No multi-question quizzes, spaced repetition, or adaptive difficulty within a session. |
| **Context not passed to writer** | `question_writer` doesn't see student's prior answers on that topic, so it repeats same difficulty. |
| **Tracing only works with OpenAI key** | Without `OPENAI_API_KEY`, traces don't appear at platform.openai.com/traces — Gemini calls are invisible. |
| **Rate limits crash the loop** | No retry/backoff on 429; session dies mid-quiz (see `main.py` line 197 `StopIteration` on empty topic list after quota exhaustion). |

## Files

- `main.py` — CLI loop, agents, tools, persistence
- `topics.json` — 6 topics from OpenAI Agents SDK course
- `student_profile.json` — persisted profile (created after first run)
- `.env` — API keys (not committed)
- `pyproject.toml` / `uv.lock` — dependencies