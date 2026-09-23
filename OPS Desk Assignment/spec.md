# Spec — Saylani Student Ops Desk

Behavioural specification. What the Desk does, not how it is implemented. Restates FR-1–FR-13 plus explicit non-goals. Source brief: `PROJECT_GUIDE.md` / `student-ops-desk-project-guide.pdf`, with model provider override: **OpenAI `gpt-4o-mini`** (not Gemini).

## Purpose

The Ops Desk is the front door for student questions about this bootcamp. A student asks in plain language; the Desk classifies intent (assignment / career / admin), answers from real course data, refuses out-of-scope questions, and closes resolved conversations with a structured ticket.

---

## Functional requirements (FR-1 – FR-13)

### FR-1 — OpenAI-backed agent, configured at the agent level

The Desk runs on **`gpt-4o-mini`** through the OpenAI Agents SDK, with the model set **on the agent** rather than only globally or per run. The entry point is asynchronous.

**Done when:** a terminal question is answered by the model; no sole reliance on a global default client for model choice; entry is an async function driven by `asyncio.run`.

### FR-2 — Course knowledge, reachable only through tools

Course facts live in **`courses.json`**. The agent reaches them **only** by calling tools. Minimum tools: list courses; fetch one course’s schedule and policies; look up an assignment by id.

**Done when:** deleting a course from the file changes answers with no code change; the Desk declines to invent an assignment id not in the file.

### FR-3 — The student is in context, never in the prompt

A `StudentProfile` is passed to every run as local context. Tools may read it. Prompt text never contains name, roll number, or tier as free prompt payload.

**Done when:** profile-reading tool schema has no wrapper parameter; grepping source finds the student’s name only in the constructed profile object.

### FR-4 — Instructions that change per turn

The system prompt is built at request time from the profile: greets by name, names the enrolled course, becomes **terser when `open_tickets >= 3`**.

**Done when:** three different profiles produce three visibly different resolved prompts; the resolved prompt can be printed before any model call.

### FR-5 — Two specialists, cloned from one base, reached by handoff

An **Assignments** specialist and a **Careers** specialist are cloned from a single base agent, differing only in instructions and model settings. The Desk transfers the conversation to the fitting specialist; **the specialist answers**, not the Desk.

- Assignments: cold, factual.  
- Careers: warmer.  

**Done when:** the answering agent is identifiable in code after the run; the handoff appears in run items; specialists share the base model without restating a different model id.

### FR-6 — One specialist exposed as a tool, not a handoff

A **Summariser** condenses a long policy answer to three lines. It is wired as a **tool** the Desk calls so the Desk keeps the conversation and speaks in its own voice.

**Done when:** rationale for tool-vs-handoff is defensible; after summarisation the final message still comes from the Desk.

### FR-7 — Every resolved conversation produces a structured ticket

Final output for a resolved query is a typed **Pydantic `Ticket`**, not prose:

- `category`: `Literal["assignment", "career", "admin"]`
- `summary`: `str`
- `next_step`: `str`
- `resolved`: `bool`
- `escalate`: `bool`

**Done when:** `type(result.final_output) is Ticket`; `resolved` is used in a Python `if`; a deliberately impossible request surfaces the SDK/Pydantic parsing error instead of a half-filled object.

### FR-8 — Input guardrail refuses non-course questions

An input guardrail rejects anything unrelated to the bootcamp **before** the Desk’s answer model runs. Program code catches the tripwire and replies politely; it must not crash.

**Done when:** off-topic → courteous refusal; refusal does not bill the model that would have answered; catch site is pointable in code.

### FR-9 — Tool gating, stopping rule, and turn ceiling

Three controls, all present:

1. **Tier gate:** a tool only offered when `tier == "scholarship"` — **absent** from the tool list for others, not refused after listing.  
2. **Stop:** `close_ticket` ends the run when called; its output becomes the final result.  
3. **Ceiling:** explicit turn ceiling **raises** rather than loops; caught and reported.  

**Done when:** same question as regular vs scholarship yields different offered tool sets; ceiling number is nameable and justified in code.

### FR-10 — Run audit trail + one watched specialist

Run-level hooks record an **ordered timeline** across every agent including handoff. Agent-level hooks attach to **exactly one** specialist.

**Done when:** one question → one timeline naming both agents in order; can explain why agent-level hooks go quiet at handoff.

### FR-11 — Custom runner wrapping every run

A custom runner stamps **request id** and **elapsed time** around every run in-process, registered once at startup. No agent definition mentions it.

**Done when:** wrapper output appears for Desk run and specialist run; no agent file references the runner.

### FR-12 — Chainlit interface with per-session memory

Usable in a browser. Agent + student profile built **once per session**, not per message. Conversation remembers earlier turns.

**Done when:** second message references the first and is understood; two browser windows do not share history; handler **awaits** the run (not a sync fire-and-forget).

### FR-13 — Traceable conversations

Tracing on, exported under the project’s own key; **one student conversation = one trace**.

**Done when:** trace opens; every span can be named; at least one unnecessary Desk call can be pointed out.

---

## Non-functional requirements (summary)

| ID | Requirement |
|----|-------------|
| NFR-1 | Secrets only in gitignored `.env`; missing key → clear startup error |
| NFR-2 | Every agent declares model settings (`gpt-4o-mini`); generation has a ceiling |
| NFR-3 | Conversations traceable; FR-10 timeline written durably, not only printed |
| NFR-4 | Tools return actionable sentences on bad data; tools never raise to the runner |
| NFR-5 | `git log`: four Phase 0 artifacts before first code commit |

---

## Three things this project will not do

1. **Will not answer out-of-scope questions** — anything not about the Saylani bootcamp course (assignments, careers within the program, course admin) is refused by the guardrail; no general chatbot, no unrelated Q&A.
2. **Will not put student identity raw into prompt text** — no name/roll/tier stuffed into the prompt as free text or tool-wrapper parameters; identity flows only via deliberate local context and profile tools (FR-3).
3. **Will not invent course facts** — no schedules, policies, or assignment ids beyond `courses.json`; no fallback “plausible” answers when data is missing.

---

## Out of production scope (this build)

- No multi-tenant production auth/billing  
- No real registrar/ERP integration (tickets are structured output for downstream systems, optional local persistence only if time remains)  
- No fine-tuning or training of models  
