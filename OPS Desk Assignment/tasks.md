# Tasks — Saylani Student Ops Desk

Ordered, small, verifiable checklist. Each task names the requirement it satisfies.  
**No `.py` tasks start until Phase 0 (these four files) is committed.**

Legend: `[ ]` open · Gate = gatekeeper PASS · Audit = requirements-auditor at phase end

---

## Phase 0 — specification gate (NO CODE)

- [ ] **T0.1** Write `constitution.md` — provider, secrets, tools-never-raise, student data rules · **NFR-1, NFR-4, FR-3, Rule 1**
- [ ] **T0.2** Write `spec.md` — FR-1–FR-13 + three non-goals · **spec completeness**
- [ ] **T0.3** Write `plan.md` — agents, ownership, tools, data structures · **architecture**
- [ ] **T0.4** Write `tasks.md` — this file · **ordered implementation**
- [ ] **T0.5** **USER:** commit only Phase 0 markdown (no `.py` in same commit) · **Rule 1, NFR-5**
- [ ] **T0.6** Run **gatekeeper** → expect `PASS` before any T1.x · **NFR-5**

---

## Phase 1 — core desk (FR-1 → FR-4)

*Pre: Gate PASS. Post: requirements-auditor PASS.*

- [ ] **T1.1** `.env` + `.env.example` + `.gitignore` for `.env`; startup loads key or raises clear `RuntimeError` · **NFR-1**
- [ ] **T1.2** Scaffold project layout (`src/` or flat modules per plan); no secrets in code · **NFR-1**
- [ ] **T1.3** Write `courses.json` (≥3 courses, unique assignment ids) · **FR-2** · *(fixture-architect skill)*
- [ ] **T1.4** Write `test_profiles.py` — regular/0, regular/3, scholarship · **FR-4, FR-9 prep** · *(fixture-architect skill)*
- [ ] **T1.5** `list_courses` tool → reads JSON only · **FR-2, NFR-4**
- [ ] **T1.6** `get_course` tool → schedule+policies; bad id → actionable sentence, no raise · **FR-2, NFR-4**
- [ ] **T1.7** `get_assignment` tool → by id; unknown id refused · **FR-2**
- [ ] **T1.8** `StudentProfile` dataclass + local context injection · **FR-3**
- [ ] **T1.9** Profile tool schema: no wrapper parameter; grep name only in profile construct · **FR-3**
- [ ] **T1.10** Dynamic instruction builder: name, course, terse if `open_tickets >= 3`; print resolved prompt pre-model · **FR-4**
- [ ] **T1.11** Desk agent: model **`gpt-4o-mini`** set **on agent**; no global-only model wiring · **FR-1, NFR-2**
- [ ] **T1.12** Named turn ceiling constant wired into run options · **FR-9, NFR-2**
- [ ] **T1.13** Async entry: `async def main` + `asyncio.run` — terminal Q&A works · **FR-1**
- [ ] **T1.14** Verify FR-1–FR-4 done-whens (three prompts differ; delete course → answer changes) · **FR-1–4**
- [ ] **T1.15** **Audit Phase 1** → punch-list empty · **NFR-1, FR-1, FR-7 prep**

---

## Phase 2 — specialists (FR-5 → FR-9)

*Pre: Phase 1 auditor PASS.*

- [ ] **T2.1** Base agent → clone Assignments (cold/factual) + Careers (warmer); shared model id not restated differently · **FR-5**
- [ ] **T2.2** Desk handoff to specialist; specialist answers; answering agent identifiable post-run; handoff in run items · **FR-5**
- [ ] **T2.3** Summariser as **tool** (`summarise_policy` ≤3 lines); Desk still speaks final voice · **FR-6**
- [ ] **T2.4** Document/defend tool-vs-handoff rationale (Summariser=tool, two specialists=handoff) · **FR-6**
- [ ] **T2.5** Pydantic `Ticket` model + output_type on final Desk response · **FR-7**
- [ ] **T2.6** Force `type(result.final_output) is Ticket`; branch on `resolved`/`escalate` · **FR-7**
- [ ] **T2.7** Impossible request → SDK/Pydantic parse error surfaced, not half object · **FR-7**
- [ ] **T2.8** Input guardrail before Desk answer path; catch tripwire → polite refusal; catch site marked; no billed Desk answer call · **FR-8**
- [ ] **T2.9** Scholarship tool **absent** from tool list when tier is regular; present when scholarship · **FR-9**
- [ ] **T2.10** `close_ticket` ends run immediately; output = final result · **FR-9**
- [ ] **T2.11** Turn ceiling raises not loops; caught + reported with chosen number · **FR-9**
- [ ] **T2.12** Same question × regular/scholarship → different tool sets demonstrated · **FR-9**
- [ ] **T2.13** **Audit Phase 2** → punch-list empty · **FR-5–9, NFR-2, FR-7**

---

## Phase 3 — operations & interface (FR-10 → FR-13)

*Pre: Phase 2 auditor PASS. Cut order if late: FR-11, FR-6 already done else keep, AgentHooks half of FR-10. Never cut FR-7/FR-8.*

- [ ] **T3.1** Run-level hooks → ordered timeline covering all agents incl. handoff · **FR-10**
- [ ] **T3.2** Persist timeline durably (file/SQLite), not print-only · **NFR-3, FR-10**
- [ ] **T3.3** Agent-level hooks on **exactly one** specialist only · **FR-10**
- [ ] **T3.4** Explain/verify agent-hooks quiet at handoff moment · **FR-10**
- [ ] **T3.5** Custom runner: `request_id` + elapsed time; register once at startup; no agent file mentions it · **FR-11** *(cut first if late)*
- [ ] **T3.6** Chainlit app; session open builds agent+profile **once**; handler **awaits** run · **FR-12**
- [ ] **T3.7** Per-session memory: second message uses first; two windows isolated · **FR-12**
- [ ] **T3.8** Tracing on + own export key; one conversation → one trace · **FR-13**
- [ ] **T3.9** Name every span; identify one unnecessary Desk call from trace · **FR-13**
- [ ] **T3.10** **Audit Phase 3** → punch-list empty · **all NFRs + FR-7**

---

## Demo & closeout

- [ ] **T4.1** One clean terminal/browser conversation · **integration**
- [ ] **T4.2** One trace opened end-to-end · **FR-13, NFR-3**
- [ ] **T4.3** One structured `Ticket` printed/typed from that run · **FR-7**
- [ ] **T4.4** `git log` review: Phase 0 commits precede first `.py` · **NFR-5**
- [ ] **T4.5** User preps viva answers for the eight defence questions · **Rule 2**

---

## Verification cheat-sheet (definition of done)

| Req | Quick check |
|-----|-------------|
| Spec first | `git log` order |
| FR-2 | Delete course from JSON → answer changes |
| FR-3 | Tool schema no wrapper; grep name |
| FR-4 | Three profiles → three prompts |
| FR-5 | Answering agent id after run |
| FR-7 | `type(final_output) is Ticket` + `if resolved` |
| FR-8 | Refusal, no Desk model bill |
| FR-9 | Two tiers → two tool sets; named ceiling |
| FR-12 | Await run; windows isolated |
| FR-13 | One conversation, one trace |
