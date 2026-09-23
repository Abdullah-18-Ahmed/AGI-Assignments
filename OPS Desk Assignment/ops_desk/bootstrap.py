"""Process startup: secrets, custom runner, tracing — called once from entrypoints (FR-11 / FR-13)."""

from __future__ import annotations

from ops_desk.config import require_openai_api_key
from ops_desk.custom_runner import register_custom_runner
from ops_desk.tracing_setup import enable_tracing

_bootstrapped = False


def bootstrap() -> str:
    """Register custom runner + enable tracing once per process. Returns API key."""
    global _bootstrapped
    key = require_openai_api_key()
    register_custom_runner()
    enable_tracing()
    _bootstrapped = True
    return key


def is_bootstrapped() -> bool:
    return _bootstrapped
