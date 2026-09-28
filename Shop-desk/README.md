# Shop Desk

AI-powered Shop Desk assistant for Al-Noor Electronics.

## Features

- **FR-1**: Catalogue Price Lookup
- **FR-2**: Stock Availability Check
- **FR-3**: SKU Search by Keyword
- **FR-4**: Category Browse
- **FR-5**: Multi-Item Price Quote
- **FR-6**: Catalogue Guardrail (price/SKU validation)
- **FR-7**: Tiered Tools (walk_in vs regular)
- **FR-8**: Pricing Specialist Tool & Turn Budget
- **FR-9**: Base Agent Cloning
- **FR-10**: Human Escalation
- **FR-11**: Cost & Token Lifecycle Hooks
- **FR-12**: Chainlit Interface (10+ turn conversations)
- **FR-13**: Single Conversation Tracing (OpenTelemetry)

## Quick Start

```bash
# Install dependencies
uv sync --all-extras

# Run tests
uv run pytest

# Run Chainlit app
uv run chainlit run app.py
```

## Configuration

Create a `.env` file with your OpenAI API key:

```env
OPENAI_API_KEY=sk-your-key-here
```

## Architecture

- **Fast Path**: Direct catalogue lookups (0 LLM calls) for price/stock/detail queries with SKU
- **Specialists**: Pricing Specialist (gpt-4o) and Escalation Specialist (gpt-4o-mini)
- **Guardrails**: All outputs validated against catalogue.json
- **Tracing**: OpenTelemetry unified session traces with per-turn spans
- **History**: 10-turn limit with active order state preservation

## Models

- Default: `openai/gpt-4o-mini` (fast path)
- Reasoning: `openai/gpt-4o` (Pricing Specialist, complex queries)