from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

from shop_desk.models.shop import (
    HistoryEntry,
    SearchResult,
    ShopContext,
    ToolError,
    ToolResult,
)


class SessionQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["get_context", "add_history", "clear", "get_last_results"]
    session_id: str
    entry: Optional[HistoryEntry] = None
    results: Optional[list[SearchResult]] = None


_SESSIONS: dict[str, ShopContext] = {}
_LAST_RESULTS: dict[str, list[SearchResult]] = {}


def session_tool(query: SessionQuery) -> ToolResult:
    if query.action == "get_context":
        ctx = _SESSIONS.get(query.session_id)
        if not ctx:
            return ToolResult.failure("SESSION_NOT_FOUND", f"Session {query.session_id} not found")
        return ToolResult.success(ctx)

    if query.action == "add_history":
        if not query.entry:
            return ToolResult.failure("INVALID_QUERY", "entry is required for add_history")
        ctx = _SESSIONS.get(query.session_id)
        if not ctx:
            return ToolResult.failure("SESSION_NOT_FOUND", f"Session {query.session_id} not found")
        ctx.history.append(query.entry)
        ctx.turn_count += 1
        if len(ctx.history) > 10:
            ctx.history = ctx.history[-10:]
        return ToolResult.success(ctx)

    if query.action == "clear":
        if query.session_id in _SESSIONS:
            del _SESSIONS[query.session_id]
        if query.session_id in _LAST_RESULTS:
            del _LAST_RESULTS[query.session_id]
        return ToolResult.success(None)

    if query.action == "get_last_results":
        results = _LAST_RESULTS.get(query.session_id, [])
        return ToolResult.success(results)

    return ToolResult.failure("INVALID_QUERY", f"Unknown action: {query.action}")


def create_session(session_id: str, shop: str = "Al-Noor Electronics", currency: str = "PKR",
                   customer_id: Optional[str] = None, tier: str = "walk_in",
                   catalogue_version: str = "1.0.0") -> ShopContext:
    ctx = ShopContext(
        session_id=session_id,
        shop=shop,
        currency=currency,
        customer_id=customer_id,
        tier=tier,
        catalogue_version=catalogue_version,
    )
    _SESSIONS[session_id] = ctx
    return ctx


def set_last_results(session_id: str, results: list[SearchResult]) -> None:
    _LAST_RESULTS[session_id] = results