from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

from shop_desk.models.shop import ShopContext, Tier

_current_context: ContextVar[Optional[ShopContext]] = ContextVar("current_context", default=None)


def set_current_context(ctx: ShopContext) -> None:
    _current_context.set(ctx)


def get_current_context() -> Optional[ShopContext]:
    return _current_context.get()


def get_tier() -> Tier:
    ctx = get_current_context()
    return ctx.tier if ctx else Tier.WALK_IN


def get_customer_id() -> Optional[str]:
    ctx = get_current_context()
    return ctx.customer_id if ctx else None


def get_shop() -> str:
    ctx = get_current_context()
    return ctx.shop if ctx else "Al-Noor Electronics"


def get_currency() -> str:
    ctx = get_current_context()
    return ctx.currency if ctx else "PKR"


def get_session_id() -> Optional[str]:
    ctx = get_current_context()
    return ctx.session_id if ctx else None


def get_catalogue_version() -> str:
    ctx = get_current_context()
    return ctx.catalogue_version if ctx else "1.0.0"


class ContextWrapper:
    def __init__(self, context: ShopContext):
        self._context = context
        self._token = None

    def __enter__(self) -> ShopContext:
        self._token = _current_context.set(self._context)
        return self._context

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._token:
            _current_context.reset(self._token)


def with_context(context: ShopContext) -> ContextWrapper:
    return ContextWrapper(context)