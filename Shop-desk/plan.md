# Architecture Plan — Shop Desk

Technical structure, agents, models, contracts, and integration details.

## 1. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Chainlit UI                              │
│  (chat interface, session state, streaming tokens)              │
└─────────────────────────┬───────────────────────────────────────┘
                          │
         ┌────────────────┼────────────────┐
         ▼                ▼                ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  Fast Path      │ │  Reasoning Path │ │  Session        │
│  Agent          │ │  Agent          │ │  Manager        │
│  (gpt-4o-mini)  │ │  (gpt-4o)       │ │  (context,      │
│  - price lookup │ │  - comparisons  │ │   history,      │
│  - stock check  │ │  - recommendations│  traces)        │
│  - SKU search   │ │  - complex Q&A  │ │                 │
└────────┬────────┘ └────────┬────────┘ └────────┬────────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             ▼
                  ┌─────────────────────┐
                  │  Tool Layer         │
                  │  - catalogue_tool   │
                  │  - trace_tool       │
                  │  - session_tool     │
                  └──────────┬──────────┘
                             │
                    ┌────────┴────────┐
                    ▼                 ▼
             ┌─────────────┐   ┌─────────────┐
             │ catalogue.json │   │ trace logs  │
             │ (hot-reload)   │   │ (JSONL)     │
             └─────────────┘   └─────────────┘
```

## 2. Agents & Model Assignments

| Agent | Model | Responsibility | Path |
|-------|-------|----------------|------|
| `PriceLookupAgent` | `openai/gpt-4o-mini` | FR-1, FR-2, FR-8 (single SKU) | Fast |
| `SearchAgent` | `openai/gpt-4o-mini` | FR-3, FR-4, FR-11 (clarification) | Fast |
| `QuoteAgent` | `openai/gpt-4o-mini` | FR-5, FR-7 (calculation only) | Fast |
| `ComparisonAgent` | `openai/gpt-4o` | FR-6, FR-9 (analysis) | Reasoning |
| `ContextAgent` | `openai/gpt-4o-mini` | FR-12 (session context) | Fast |
| `TraceAgent` | `openai/gpt-4o-mini` | FR-13 (usage reporting) | Fast |
| `RouterAgent` | `openai/gpt-4o-mini` | Classify intent → route to above | Fast |

**Routing Rules (deterministic, not model-decided):**
- Single SKU lookup (price, stock, detail) → `PriceLookupAgent`
- Keyword/category search → `SearchAgent`
- Multi-SKU quote/summary → `QuoteAgent`
- Comparison (2–5 SKUs), recommendation, "which is better" → `ComparisonAgent`
- Ambiguous reference ("that one", "the blue one") → `ContextAgent` → resolve → route
- Usage/cost query → `TraceAgent`
- Everything else → `RouterAgent` classifies intent

## 3. Typed Data Models (Pydantic)

```python
# models/shop.py
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, Literal
from decimal import Decimal
from enum import Enum

class Path(str, Enum):
    FAST = "fast"
    REASONING = "reasoning"

class ShopContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    session_id: str
    turn_count: int = 0
    history: list["HistoryEntry"] = Field(default_factory=list)
    last_results: list["SearchResult"] = Field(default_factory=list)
    catalogue_version: str

class HistoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str
    path: Optional[Path] = None
    tokens: Optional["TokenUsage"] = None
    timestamp: float

class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: str

class CatalogueEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: str
    name: str
    category: str
    price: Decimal  # exact from JSON
    stock: int
    description: str = ""
    weight_g: Optional[int] = None
    dimensions_cm: Optional[dict] = None  # {"l": 10, "w": 5, "h": 2}
    tags: list[str] = Field(default_factory=list)

class LineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: str
    name: str
    unit_price: Decimal
    quantity: int = Field(ge=1)
    line_total: Decimal  # unit_price * quantity

class Order(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[LineItem]
    subtotal: Decimal
    tax: Decimal
    shipping: Decimal
    grand_total: Decimal
    currency: str = "USD"

class SearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: str
    name: str
    price: Decimal
    stock: int
    category: str
    relevance_score: float  # 0.0–1.0

class ToolResult(BaseModel, generic=True):
    model_config = ConfigDict(extra="forbid")
    ok: bool
    data: Optional[T] = None
    error: Optional["ToolError"] = None

class ToolError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    message: str
```

## 4. Tool Contracts

### catalogue_tool
```python
# Input
class CatalogueQuery(BaseModel):
    action: Literal["get", "search", "category", "multi_get", "version"]
    sku: Optional[str] = None
    skus: Optional[list[str]] = None
    query: Optional[str] = None
    category: Optional[str] = None
    page: int = 1
    page_size: int = 20

# Output (ToolResult)
# ok=true: data = CatalogueEntry | list[CatalogueEntry] | SearchResult | str(version)
# ok=false: error = {code: "NOT_FOUND"|"INVALID_QUERY"|"VERSION_MISMATCH", message: str}
```

### trace_tool
```python
# Input
class TraceQuery(BaseModel):
    action: Literal["log", "session_summary", "export"]
    entry: Optional["TraceEntry"] = None  # for log
    session_id: Optional[str] = None      # for summary/export

# TraceEntry
class TraceEntry(BaseModel):
    model: str
    path: Path
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    turn_count: int
    agent: str
    timestamp: float

# Output (ToolResult)
# ok=true: data = SessionSummary | list[TraceEntry] | None
# ok=false: error = {code: "SESSION_NOT_FOUND", message: str}
```

### session_tool
```python
# Input
class SessionQuery(BaseModel):
    action: Literal["get_context", "add_history", "clear", "get_last_results"]
    session_id: str
    entry: Optional[HistoryEntry] = None  # for add_history
    results: Optional[list[SearchResult]] = None  # for caching last results

# Output (ToolResult)
# ok=true: data = ShopContext | list[SearchResult] | None
# ok=false: error = {code: "SESSION_NOT_FOUND", message: str}
```

## 5. Handoff Filters (Agent → Agent)

| From | To | Trigger | Payload |
|------|-----|---------|---------|
| `RouterAgent` | `PriceLookupAgent` | intent=price_lookup | `{sku: str}` |
| `RouterAgent` | `SearchAgent` | intent=search | `{query: str}` |
| `RouterAgent` | `QuoteAgent` | intent=multi_quote | `{items: list[{sku, qty}]}` |
| `RouterAgent` | `ComparisonAgent` | intent=compare | `{skus: list[str]}` |
| `RouterAgent` | `ContextAgent` | intent=ambiguous | `{query: str, candidates: list[SearchResult]}` |
| `ContextAgent` | `PriceLookupAgent` | resolved to SKU | `{sku: str}` |
| `ContextAgent` | `SearchAgent` | need more candidates | `{query: str}` |
| `Any Agent` | `TraceAgent` | user asks for usage | `{session_id: str}` |

Handoff is a function call, not a prompt. The receiving agent gets typed input, produces typed output.

## 6. Chainlit Integration

- **Entry point**: `app.py` → `on_chat_start` initializes `ShopContext`, loads catalogue version.
- **Message handling**: `on_message` → `RouterAgent.route()` → selected agent → stream response.
- **Streaming**: Agents yield tokens via Chainlit `stream_token`; final message assembled for history.
- **Session state**: Stored in Chainlit `user_session` (dict) keyed by `session_id`.
- **Catalogue hot-reload**: File watcher on `catalogue.json` → updates in-memory cache → increments version.
- **Trace logging**: Every agent call wraps SDK call, extracts `usage`, calls `trace_tool.log()`.
- **Error display**: Tool `ok=false` → user-friendly message via `cl.Message(content=error.message, author="System")`.

## 7. Directory Structure

```
shop_desk/
├── agents/
│   ├── __init__.py
│   ├── base.py              # BaseAgent with model, tools, tracing
│   ├── router.py            # RouterAgent
│   ├── price_lookup.py      # PriceLookupAgent
│   ├── search.py            # SearchAgent
│   ├── quote.py             # QuoteAgent
│   ├── comparison.py        # ComparisonAgent
│   ├── context.py           # ContextAgent
│   └── trace.py             # TraceAgent
├── models/
│   ├── __init__.py
│   └── shop.py              # Pydantic models (see §3)
├── tools/
│   ├── __init__.py
│   ├── catalogue.py         # catalogue_tool
│   ├── trace.py             # trace_tool
│   └── session.py           # session_tool
├── catalogue/
│   └── catalogue.json       # source of truth
├── prompts/
│   ├── system_fast.md       # system prompt for fast-path agents
│   ├── system_reasoning.md  # system prompt for reasoning agent
│   └── templates/           # jinja2 prompt templates
├── config/
│   ├── __init__.py
│   └── settings.py          # Pydantic Settings from .env
├── app.py                   # Chainlit entry point
└── main.py                  # CLI entry (optional)
tests/
├── test_fr1_price_lookup.py
├── test_fr2_stock.py
...
├── test_guardrails.py
├── test_trace.py
└── conftest.py
```

## 8. Configuration (`.env`)

```bash
OPENAI_API_KEY=sk-...
CATALOGUE_PATH=./catalogue/catalogue.json
CATALOGUE_VERSION=1.0.0
LOW_STOCK_THRESHOLD=5
TAX_RATE=0.08
SHIPPING_FLAT=5.99
DEFAULT_PAGE_SIZE=20
MAX_HISTORY_TURNS=5
FAST_MODEL=openai/gpt-4o-mini
REASONING_MODEL=openai/gpt-4o
TRACE_LOG_PATH=./logs/traces.jsonl
```

## 9. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Model hallucinates price | Post-generation guardrail validates every price/SKU against catalogue |
| Routing misclassifies intent | Deterministic keyword/regex router; model only for ambiguous fallback |
| Catalogue stale | Hot-reload + version check on every query |
| Token costs unbounded | Fast path forced for 80%+ queries; reasoning path requires explicit trigger |
| Chainlit blocks on sync calls | All tools async; agents use `asyncio.to_thread` for SDK calls |

---

## Traceability Matrix

| FR | Agent(s) | Tool(s) | Tests |
|----|----------|---------|-------|
| FR-1 | PriceLookupAgent | catalogue_tool | test_fr1_price_lookup.py |
| FR-2 | PriceLookupAgent | catalogue_tool | test_fr2_stock.py |
| FR-3 | SearchAgent | catalogue_tool | test_fr3_search.py |
| FR-4 | SearchAgent | catalogue_tool | test_fr4_category.py |
| FR-5 | QuoteAgent | catalogue_tool | test_fr5_multi_quote.py |
| FR-6 | ComparisonAgent | catalogue_tool | test_fr6_compare.py |
| FR-7 | QuoteAgent | catalogue_tool | test_fr7_order_summary.py |
| FR-8 | PriceLookupAgent | catalogue_tool | test_fr8_detail.py |
| FR-9 | ComparisonAgent | catalogue_tool | test_fr9_low_stock.py |
| FR-10 | RouterAgent → PriceLookupAgent | catalogue_tool | test_fr10_invalid_sku.py |
| FR-11 | SearchAgent | catalogue_tool | test_fr11_clarify.py |
| FR-12 | ContextAgent | session_tool | test_fr12_context.py |
| FR-13 | TraceAgent | trace_tool | test_fr13_trace.py |