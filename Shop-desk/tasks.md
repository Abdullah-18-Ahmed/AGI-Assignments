# Implementation Tasks — Shop Desk

Ordered, independently verifiable tasks. Each task maps to one or more FRs. Checkboxes for tracking.

## Phase 0: Foundation (No FR — Prerequisites)

- [ ] **T0.1** Create Python project structure per `plan.md` §7 (directories, `__init__.py` files)
- [ ] **T0.2** Add `pyproject.toml` with dependencies: `openai`, `pydantic`, `pydantic-settings`, `chainlit`, `python-dotenv`, `pytest`, `pytest-asyncio`, `watchfiles`
- [ ] **T0.3** Create `.env.example` with all keys from `plan.md` §8 (no real values)
- [ ] **T0.4** Create `config/settings.py` — Pydantic Settings loading from `.env`
- [ ] **T0.5** Create `catalogue/catalogue.json` with ≥20 sample SKUs across ≥3 categories (fields per `CatalogueEntry` model)
- [ ] **T0.6** Create `models/shop.py` with all Pydantic models from `plan.md` §3
- [ ] **T0.7** Create `tools/catalogue.py` — `catalogue_tool` with hot-reload + version check
- [ ] **T0.8** Create `tools/trace.py` — `trace_tool` logging to JSONL
- [ ] **T0.9** Create `tools/session.py` — `session_tool` using Chainlit `user_session`
- [ ] **T0.10** Create `agents/base.py` — `BaseAgent` with model selection, tool calling, trace wrapper
- [ ] **T0.11** Create `prompts/system_fast.md` and `prompts/system_reasoning.md`
- [ ] **T0.12** Create `app.py` — Chainlit entry with `on_chat_start`, `on_message` skeleton

## Phase 1: Fast-Path Agents (FR-1, FR-2, FR-3, FR-4, FR-8, FR-10, FR-11)

- [ ] **T1.1** Implement `PriceLookupAgent` (`agents/price_lookup.py`) — handles FR-1, FR-2, FR-8
  - Input: `sku` → calls `catalogue_tool.get` → validates price/SKU match → returns formatted response
  - Guardrail: post-generation price/SKU verification against catalogue
- [ ] **T1.2** Implement `SearchAgent` (`agents/search.py`) — handles FR-3, FR-4, FR-11
  - `search`: keyword fuzzy match → returns `SearchResult` list (max 10)
  - `category`: filter by category → paginated results
  - `clarify`: ambiguous query → returns top 3 candidates for disambiguation
- [ ] **T1.3** Implement `RouterAgent` (`agents/router.py`) — deterministic intent classification
  - Rules: SKU pattern → price_lookup; "compare X vs Y" → compare; list of SKUs → multi_quote; etc.
  - Fallback: keyword scoring → if ambiguous → handoff to `ContextAgent`
- [ ] **T1.4** Wire `RouterAgent` → `PriceLookupAgent` / `SearchAgent` handoffs in `app.py`
- [ ] **T1.5** Add FR-10 handling: unknown SKU → `catalogue_tool` returns `NOT_FOUND` → agent responds with "SKU not found" + search suggestions
- [ ] **T1.6** Create tests: `tests/test_fr1_price_lookup.py`, `tests/test_fr2_stock.py`, `tests/test_fr3_search.py`, `tests/test_fr4_category.py`, `tests/test_fr8_detail.py`, `tests/test_fr10_invalid_sku.py`, `tests/test_fr11_clarify.py`
- [ ] **T1.7** Run Phase 1 tests → all PASS

## Phase 2: Multi-Item & Reasoning Agents (FR-5, FR-6, FR-7, FR-9)

- [ ] **T2.1** Implement `QuoteAgent` (`agents/quote.py`) — handles FR-5, FR-7
  - Input: `items: list[{sku, qty}]` → `catalogue_tool.multi_get` → computes line totals, subtotal, tax, shipping, grand total
  - Returns `Order` model; formatted for user
- [ ] **T2.2** Implement `ComparisonAgent` (`agents/comparison.py`) — handles FR-6, FR-9
  - Input: `skus: list[str]` (2–5) → `catalogue_tool.multi_get` → side-by-side table
  - FR-9: on init/reload, scan catalogue for stock ≤ threshold → optional proactive alert
- [ ] **T2.3** Wire `RouterAgent` → `QuoteAgent` / `ComparisonAgent` handoffs
- [ ] **T2.4** Create tests: `tests/test_fr5_multi_quote.py`, `tests/test_fr6_compare.py`, `tests/test_fr7_order_summary.py`, `tests/test_fr9_low_stock.py`
- [ ] **T2.5** Run Phase 2 tests → all PASS

## Phase 3: Session Context & Tracing (FR-12, FR-13)

- [ ] **T3.1** Implement `ContextAgent` (`agents/context.py`) — handles FR-12
  - Uses `session_tool.get_last_results` to resolve "that one", "the second one"
  - Maintains last 5 turns in `ShopContext.history`
- [ ] **T3.2** Implement `TraceAgent` (`agents/trace.py`) — handles FR-13
  - `trace_tool.session_summary` → formats tokens, turns, model distribution, estimated cost
- [ ] **T3.3** Integrate `trace_tool.log()` into `BaseAgent` — every model call auto-logs
- [ ] **T3.4** Add session context to `app.py` — `on_chat_start` creates `ShopContext`, `on_message` updates history
- [ ] **T3.5** Create tests: `tests/test_fr12_context.py`, `tests/test_fr13_trace.py`
- [ ] **T3.6** Run Phase 3 tests → all PASS

## Phase 4: Guardrails, Polish, E2E (All FRs)

- [ ] **T4.1** Implement post-generation guardrail in `BaseAgent` — validates every response price/SKU against catalogue before sending
  - On mismatch: replace with catalogue value + note "corrected from catalogue"
  - On hallucinated SKU: respond "SKU not found" + search suggestions
- [ ] **T4.2** Add catalogue hot-reload: `watchfiles` watches `catalogue.json` → reload cache → bump version
- [ ] **T4.3** Create `tests/test_guardrails.py` — probes: non-existent SKU, forced fake price, price mismatch, orphan price
- [ ] **T4.4** Create `tests/test_trace.py` — verifies token logging, turn counts, model distribution, no secrets in logs
- [ ] **T4.5** Run full test suite → all PASS
- [ ] **T4.6** Manual E2E via Chainlit: verify FR-1..FR-13 work in UI
- [ ] **T4.7** Run `spec-checker` on all 4 artifacts → STATUS: PASS
- [ ] **T4.8** Run `code-auditor` on source → no BLOCKER findings
- [ ] **T4.9** Run `test-runner` → all FRs PASS

---

## Task → FR Mapping

| Task | FRs |
|------|-----|
| T1.1 | FR-1, FR-2, FR-8 |
| T1.2 | FR-3, FR-4, FR-11 |
| T1.3 | FR-1..FR-13 (routing) |
| T1.5 | FR-10 |
| T2.1 | FR-5, FR-7 |
| T2.2 | FR-6, FR-9 |
| T3.1 | FR-12 |
| T3.2 | FR-13 |
| T4.1 | FR-1..FR-13 (guardrail) |
| T4.3 | Guardrail NFR |

---

## Verification Checklist (per Phase)

| Phase | Spec Check | Unit Tests | Guardrail Probes | Trace Check | Code Audit |
|-------|------------|------------|------------------|-------------|------------|
| 0     | ✓          | —          | —                | —           | ✓          |
| 1     | ✓          | T1.6       | T4.3 (partial)   | —           | ✓          |
| 2     | ✓          | T2.4       | T4.3 (partial)   | —           | ✓          |
| 3     | ✓          | T3.5       | T4.3 (partial)   | T3.3        | ✓          |
| 4     | ✓          | T4.5       | T4.3 (full)      | T4.4        | ✓          |

---

## Done Criteria

All phases complete when:
1. `spec-checker` → `STATUS: PASS` on all 4 artifacts
2. Full test suite → 0 failures, all FR-1..FR-13 `PASS`
3. `code-auditor` → 0 BLOCKER findings
4. `check-guardrails` skill → `PASS` on probe suite
5. `trace-cost` skill → `OK` (no gaps)
6. Chainlit UI → manual E2E for FR-1..FR-13 succeeds