# Specification — Shop Desk

Behavioral specification for the AI-powered Shop Desk assistant. All requirements trace to `constitution.md`.

## Functional Requirements (FR-1 through FR-13)

### FR-1: Catalogue Price Lookup
Given a valid SKU from `catalogue.json`, the assistant returns the exact price (currency + amount) for that SKU. Response includes SKU, product name, and price. No model-generated prices.

### FR-2: Stock Availability Check
Given a valid SKU, the assistant returns current stock level (integer) from `catalogue.json`. If stock is 0, explicitly states "out of stock". No model-inferred availability.

### FR-3: SKU Search by Name/Keyword
User provides a product name fragment or keyword. Assistant returns matching SKUs (exact + fuzzy) with names and prices from `catalogue.json`. Results ranked by relevance; max 10 results.

### FR-4: Category Browse
User requests a category (e.g., "electronics", "clothing"). Assistant returns all SKUs in that category from `catalogue.json` with name, price, and stock. Supports pagination (page size configurable, default 20).

### FR-5: Multi-Item Price Quote
User provides a list of SKUs + quantities. Assistant returns a line-item breakdown (SKU, name, unit price, qty, line total) and grand total. All prices from `catalogue.json`. Validates each SKU exists; rejects unknown SKUs with explicit error.

### FR-6: Price Comparison
User provides 2–5 SKUs. Assistant returns a side-by-side comparison table: SKU, name, unit price, stock, category. All values from `catalogue.json`. No model opinion on "better value".

### FR-7: Order Summary Confirmation
Given a confirmed list of line items (SKU, qty), assistant produces a final order summary: line items with prices, subtotal, tax (fixed rate from config), shipping (fixed from config), grand total. Prices strictly from `catalogue.json`. Output formatted for copy-paste.

### FR-8: Product Detail Lookup
User requests full details for a SKU. Assistant returns: SKU, name, category, price, stock, description, weight/dimensions (if in catalogue), tags. All fields verbatim from `catalogue.json`.

### FR-9: Low-Stock Alert (Proactive)
On session start or catalogue reload, if any SKU has stock ≤ threshold (config, default 5), assistant may surface a brief alert listing affected SKUs. Data from `catalogue.json` only.

### FR-10: Invalid SKU Handling
User references a SKU not in `catalogue.json`. Assistant responds with "SKU not found" and suggests valid alternatives via FR-3 search. Never invents a price or description.

### FR-11: Ambiguous Query Clarification
User asks an ambiguous question (e.g., "how much is the blue one?"). Assistant asks a clarifying question listing candidate SKUs from catalogue (max 3). Does not guess.

### FR-12: Session Context Retention
Within a Chainlit session, the assistant remembers the last 5 user queries and their results. References prior results by SKU when user says "that one" or "the second one". Context cleared on new session or explicit reset.

### FR-13: Cost & Trace Transparency
On user request (e.g., "show usage"), assistant displays session aggregates: total tokens (prompt/completion), turn count, model distribution (fast vs reasoning), estimated cost (if pricing config present). Data from trace logs, not estimated.

---

## Non-Goals (Explicitly NOT Implemented)

1. **No Checkout / Payments / Cart Persistence** — The Desk provides quotes and summaries only. No payment processing, no cart storage across sessions, no order submission to external systems.

2. **No User Accounts / Authentication / Personal Data** — No login, no user profiles, no purchase history, no PII collection. Sessions are anonymous and ephemeral.

3. **No Dynamic Pricing / Promotions / Discounts** — Prices are exactly what `catalogue.json` states. No coupon codes, loyalty discounts, time-based pricing, or model-suggested "deals". If it's not in the catalogue, it doesn't exist.

---

## Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-1 | Fast-path latency ≤ 500ms p95 (local catalogue lookup + gpt-4o-mini single turn) |
| NFR-2 | Reasoning-path latency ≤ 3s p95 (gpt-4o multi-turn) |
| NFR-3 | 100% price/SKU accuracy vs catalogue (guardrail-enforced) |
| NFR-4 | Zero unhandled exceptions surfaced to user (tools return structured errors) |
| NFR-5 | Token usage logged for 100% of model calls |
| NFR-6 | Chainlit UI responsive; no blocking calls on main thread |
| NFR-7 | Catalogue reload without process restart (hot-reload on file change) |

---

## Acceptance Criteria

- All FR-1..FR-13 have at least one automated test in `tests/`.
- `spec-checker` reports `STATUS: PASS` on all four artifacts.
- `code-auditor` reports no BLOCKER findings.
- `test-runner` executes full suite with `PASS` and all FRs `PASS` or `UNVERIFIED` (no `FAIL`).