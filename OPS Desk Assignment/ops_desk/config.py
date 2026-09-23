"""Startup configuration: secrets and run ceilings (NFR-1, NFR-2, FR-9)."""

from __future__ import annotations

import os

from dotenv import load_dotenv

# Explicit turn ceiling — named constant (NFR-2 / FR-9). Raise/reports rather than loop.
MAX_TURNS: int = 12

# Agent-level model id (FR-1, NFR-2). Not a process-global default-only setting.
AGENT_MODEL: str = "gpt-4o-mini"


def require_openai_api_key() -> str:
    """Load .env and return OPENAI_API_KEY, or raise a clear startup error (NFR-1)."""
    load_dotenv()
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key or key.startswith("sk-your-key"):
        raise RuntimeError(
            "OPENAI_API_KEY is missing or still a placeholder. "
            "Copy .env.example to .env and set OPENAI_API_KEY to your OpenAI key."
        )
    if key.lower().startswith("sk-") is False and len(key) < 20:
        raise RuntimeError(
            "OPENAI_API_KEY does not look like a valid OpenAI key. "
            "Update .env and restart."
        )
    return key
