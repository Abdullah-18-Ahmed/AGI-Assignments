# Plan — Saylani Student Ops Desk architecture

Spec-Kit-Plus Phase 0. Architecture only — no code in this phase.

## 1. Agents

| Agent | Role | Model | Conversation ownership |
|-------|------|-------|------------------------|
| **Ops Desk (Desk)** | Front door: classify, guardrail, tools, ticket, voice | `gpt-4o-mini` @ agent level | **Owns the conversation by default** — greets, runs tools, emits final `Ticket` unless handed off |
| **Assignments specialist** | Cold, factual assignment help | `gpt-4o-mini` (cloned from base; no restated divergent model id) | Answers **during handoff only**; returns control after answer |
| **Careers specialist** | Warmer career guidance | `gpt-4o-mini` (clone) | Same — handoff target |
| **Summariser** | 3-line condensation of long policy text | `gpt-4o-mini` (clone) | **Never owns conversation** — exposed as a **tool** (FR-6) |

**Base clone:** one base agent definition → clone → adjust instructions + deliberate model settings (temperature etc.) only. Shared: model id, tool permission patterns from base unless instruction-level override is deliberate.

**Who owns the conversation:** the **Desk**. Handoff (FR-5) transfers a turn to Assignments or Careers for the specialist’s reply; the Desk remains responsible for guardrails, tools, summariser calls, and **always produces the structured `Ticket`** on resolution.

```
Student → [Input guardrail] → Desk
                               ├─ tool calls (courses / profile / close_ticket / summarise…)
                               ├─ handoff → Assignments | Careers → back to run → Desk finalizes
                               └─ Ticket (FR-7)
```

## 2. Tools (name → returns)

| Tool name | Caller | Returns | Notes |
|-----------|--------|---------|-------|
| `list_courses` | Desk (and specialists if allowed) | `list[CourseSummary]` or JSON string of course id+title | Reads `courses.json` only |
| `get_course` | Desk | `CourseDetail` (schedule, policies, assignments) | Unknown id → actionable sentence, no raise (NFR-4) |
| `get_assignment` | Desk | `AssignmentDetail` \| error sentence | id must exist in file (FR-2) |
| `get_profile_field` / profile read | Desk, specialists | Requested non-secret profile field(s) | Schema **no wrapper param** (FR-3) |
| `summarise_policy` | Desk | `str` (≤3 lines) | Backed by Summariser agent-as-tool (FR-6) |
| `scholarship_ resources` (name TBD in code, e.g. `get_scholarship_benefits`) | Desk | Scholarship-only payload or sentence | **Omitted** from tool list when `tier != "scholarship"` (FR-9) |
| `close_ticket` | Desk | Final output object / terminal result | **Stops run immediately** when called (FR-9) |

All tools: catch internal errors → return model-actionable sentence; **never raise** to runner (NFR-4).

## 3. Data structures crossing boundaries

### StudentProfile (local context → tools / instruction builder)

```text
StudentProfile
  name: str
  roll_no: str
  course_id: str
  tier: "regular" | "scholarship"
  open_tickets: int
```

Passed as **local context** each run; not serialized into prompt as identity dump.

### Ticket (agent final_output → caller / UI / audit)

```text
Ticket (Pydantic BaseModel)
  category: Literal["assignment", "career", "admin"]
  summary: str
  next_step: str
  resolved: bool
  escalate: bool
```

### courses.json (disk → tools only)

```text
CoursesFile
  courses: list[Course]
Course
  id, title, schedule: str
  policies: dict[str, str]
  assignments: list[Assignment]
Assignment
  id, title, due: str
```

### Run audit timeline (hooks → durable sink)

```text
TimelineEvent
  seq: int
  timestamp: float
  agent_name: str
  event: str          # start | llm | tool | handoff | end | …
  detail: str         # non-sensitive
```

### Custom runner stamp (wrapper → logs)

```text
RunStamp
  request_id: str
  elapsed_ms: float
  agent_name: str
```

### Session state (Chainlit session → Desk)

```text
SessionState
  profile: StudentProfile          # built once on session open
  agent: Desk agent                # built once on session open
  history: conversation turns      # per window; isolated across windows
```

## 4. Process layout

| Surface | Entry |
|---------|--------|
| Terminal demo | `async def main()` → `asyncio.run(main())` |
| Browser | Chainlit `on_message` **awaits** run; session init builds agent+profile once |
| Observability | Run hooks → timeline (FR-10, NFR-3 durable); tracing export (FR-13); custom runner registered once (FR-11) |

## 5. Config & secrets

- `.env`: `OPENAI_API_KEY=...` only  
- `.gitignore`: `.env`  
- Startup: load env → if missing key → clear `RuntimeError`  

## 6. Phase mapping (implementation order)

| Phase | FRs |
|-------|-----|
| 1 Core desk | FR-1, FR-2, FR-3, FR-4 |
| 2 Specialists | FR-5, FR-6, FR-7, FR-8, FR-9 |
| 3 Operations & UI | FR-10, FR-11, FR-12, FR-13 |

Cut list if late: FR-11, then FR-6, then AgentHooks half of FR-10. **Never cut FR-7 or FR-8.**

## 7. Validation strategy (fixtures)

- `courses.json` ≥ 3 diverse courses, unique assignment ids  
- `test_profiles.py`: regular/0 tickets, regular/3 tickets (FR-4 terse), scholarship (FR-9)  
- Requirements auditor at each phase exit (NFR-1, NFR-2/FR-1, FR-7)  
