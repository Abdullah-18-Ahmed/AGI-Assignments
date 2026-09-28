# Constitution — Shop Desk

Non-negotiable rules for the Shop Desk project. Any change to this file requires explicit approval.

## 1. Model Policy
- **Default model**: `openai/gpt-4o-mini` — used for all fast-path, single-turn operations (price lookup, stock check, SKU search, simple Q&A).
- **Reasoning override**: `openai/gpt-4o` — only invoked by explicit routing decision for multi-turn reasoning (comparisons, recommendations, complex orders, dispute resolution).
- No other models (Gemini, Claude, local, etc.) are permitted anywhere in the codebase, config, or prompts.

## 2. Catalogue Guardrails
- All prices and SKUs in assistant output **must** originate from `catalogue.json`.
- The model is **never** the source of truth for pricing or SKU validity.
- A deterministic post-generation validation step runs on every response before it reaches the user.
- Violations (hallucinated SKU, price mismatch, orphan price) → response is corrected from catalogue or replaced with a safe fallback; never passed through with only a warning.

## 3. Secrets & Configuration
- `OPENAI_API_KEY` is read **only** from `.env` at process start.
- The key is never logged, printed, committed, or embedded in prompts, traces, or error messages.
- No other secrets (database URLs, webhook tokens, etc.) are hardcoded.

## 4. Tool Safety
- **No tool raises exceptions to the runner**. Every tool returns a structured result object:
  - Success: `{ ok: true, data: ... }`
  - Failure: `{ ok: false, error: { code: string, message: string } }`
- The runner/agent handles `ok: false` gracefully — retries, falls back, or surfaces a user-friendly message.
- Tools are pure functions where possible; side effects (API calls, DB writes) are isolated and idempotent.

## 5. Observability
- Every model call logs: `model`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `turn_count`, `path` (fast | reasoning).
- Token counts come from the SDK `usage` object, not estimates.
- Turn counts reflect actual message history length.
- No PII or secrets in trace logs.

## 6. Determinism & Testability
- Fast-path routing is deterministic (rule-based, not model-decided).
- Given the same input + catalogue state, the fast path produces identical outputs.
- Multi-turn reasoning paths are seeded where practical; non-determinism is confined and documented.

## 7. Versioning
- `catalogue.json` has a `version` field. The assistant refuses to answer if the loaded version mismatches the expected version.
- Prompt templates are versioned and loaded from files, not inlined.

## 8. Non-Goals (Enforced by Constitution)
- No autonomous purchasing, payments, or cart checkout.
- No user authentication, accounts, or personal data storage.
- No dynamic pricing, discounts, or promotions not explicitly in `catalogue.json`.

---

**Violation of any rule above is a blocker.** Code that contradicts this constitution will not be merged.