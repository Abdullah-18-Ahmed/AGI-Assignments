"""FR-13 / startup — tracing on, exported under the OpenAI key; one conversation = one trace group."""

from __future__ import annotations

from agents import RunConfig, set_tracing_disabled, set_tracing_export_api_key
from agents.tracing import TracingConfig

from ops_desk.config import require_openai_api_key

WORKFLOW_NAME = "SaylaniOpsDesk"

_tracing_ready = False


def enable_tracing() -> str:
    """Turn tracing on and export under this project's OpenAI key (FR-13).

    Safe to call multiple times.
    """
    global _tracing_ready
    api_key = require_openai_api_key()
    set_tracing_disabled(False)
    set_tracing_export_api_key(api_key)
    _tracing_ready = True
    return api_key


def tracing_enabled() -> bool:
    return _tracing_ready


def conversation_run_config(conversation_id: str) -> RunConfig:
    """RunConfig so one student conversation groups as one trace (group_id + workflow)."""
    api_key = require_openai_api_key()
    return RunConfig(
        workflow_name=WORKFLOW_NAME,
        group_id=conversation_id,
        tracing=TracingConfig(api_key=api_key),
        tracing_disabled=False,
    )
