from __future__ import annotations

import json
import threading
from pathlib import Path as PathLib
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

from shop_desk.config.settings import get_settings
from shop_desk.models.shop import (
    Path as ShopPath,
    SessionSummary,
    ToolError,
    ToolResult,
    TraceEntry,
)

_TRACE_LOCK = threading.Lock()


class TraceQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["log", "session_summary", "export"]
    entry: Optional[TraceEntry] = None
    session_id: Optional[str] = None


_SESSION_TRACES: dict[str, list[TraceEntry]] = {}


def _get_log_path() -> PathLib:
    settings = get_settings()
    path = PathLib(settings.trace_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _append_to_file(entry: TraceEntry) -> None:
    path = _get_log_path()
    with _TRACE_LOCK:
        with path.open("a", encoding="utf-8") as f:
            f.write(entry.model_dump_json() + "\n")


def trace_tool(query: TraceQuery) -> ToolResult:
    if query.action == "log":
        if not query.entry:
            return ToolResult.failure("INVALID_QUERY", "entry is required for log action")
        _append_to_file(query.entry)
        session_id = query.entry.session_id if hasattr(query.entry, 'session_id') else "unknown"
        if session_id not in _SESSION_TRACES:
            _SESSION_TRACES[session_id] = []
        _SESSION_TRACES[session_id].append(query.entry)
        return ToolResult.success(None)

    if query.action == "session_summary":
        if not query.session_id:
            return ToolResult.failure("INVALID_QUERY", "session_id is required for session_summary")
        traces = _SESSION_TRACES.get(query.session_id, [])
        if not traces:
            return ToolResult.failure("SESSION_NOT_FOUND", f"No traces for session {query.session_id}")

        total_turns = len(traces)
        total_prompt = sum(t.prompt_tokens for t in traces)
        total_completion = sum(t.completion_tokens for t in traces)
        model_dist: dict[str, int] = {}
        path_dist: dict[str, int] = {}

        for t in traces:
            model_dist[t.model] = model_dist.get(t.model, 0) + 1
            path_dist[t.path.value] = path_dist.get(t.path.value, 0) + 1

        summary = SessionSummary(
            session_id=query.session_id,
            total_turns=total_turns,
            total_prompt_tokens=total_prompt,
            total_completion_tokens=total_completion,
            total_tokens=total_prompt + total_completion,
            model_distribution=model_dist,
            path_distribution=path_dist,
        )
        return ToolResult.success(summary)

    if query.action == "export":
        if not query.session_id:
            return ToolResult.failure("INVALID_QUERY", "session_id is required for export")
        traces = _SESSION_TRACES.get(query.session_id, [])
        return ToolResult.success(traces)

    return ToolResult.failure("INVALID_QUERY", f"Unknown action: {query.action}")