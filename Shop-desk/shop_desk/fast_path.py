from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from shop_desk.models.shop import CatalogueEntry, ShopContext, ToolResult
from shop_desk.tools import catalogue_tool, CatalogueQuery


@dataclass
class FastPathResult:
    handled: bool
    response: Optional[str] = None
    tool_calls: int = 0
    error: Optional[str] = None


SKU_PATTERN = re.compile(r'ANE-[A-Z]{2}-\d{3}', re.IGNORECASE)

PRICE_KEYWORDS = {"price", "cost", "how much", "pricing", "rate"}
STOCK_KEYWORDS = {"stock", "availability", "available", "in stock", "quantity", "qty"}
DETAIL_KEYWORDS = {"detail", "details", "spec", "specs", "specification", "describe", "information", "info"}


def extract_sku(text: str) -> Optional[str]:
    """Extract SKU from text if present."""
    match = SKU_PATTERN.search(text.upper())
    return match.group(0) if match else None


def detect_intent(text: str) -> Optional[str]:
    """Detect if text is a simple price/stock/detail query."""
    text_lower = text.lower()
    
    has_sku = extract_sku(text) is not None
    
    if has_sku:
        if any(kw in text_lower for kw in PRICE_KEYWORDS):
            return "price"
        if any(kw in text_lower for kw in STOCK_KEYWORDS):
            return "stock"
        if any(kw in text_lower for kw in DETAIL_KEYWORDS):
            return "detail"
        return "price"
    
    return None


async def fast_path_price_lookup(sku: str, context: ShopContext) -> FastPathResult:
    """Direct catalogue lookup for price - NO LLM CALL."""
    result = catalogue_tool(CatalogueQuery(action="get", sku=sku))
    if not result.ok:
        return FastPathResult(
            handled=True,
            tool_calls=1,
            error=result.error.message if result.error else "Unknown error"
        )
    
    entry: CatalogueEntry = result.data
    response = f"SKU: {entry.sku} | Product: {entry.name} | Price: {context.currency} {entry.price:,}"
    return FastPathResult(handled=True, response=response, tool_calls=1)


async def fast_path_stock_check(sku: str, context: ShopContext) -> FastPathResult:
    """Direct catalogue lookup for stock - NO LLM CALL."""
    result = catalogue_tool(CatalogueQuery(action="get", sku=sku))
    if not result.ok:
        return FastPathResult(
            handled=True,
            tool_calls=1,
            error=result.error.message if result.error else "Unknown error"
        )
    
    entry: CatalogueEntry = result.data
    stock_status = "out of stock" if entry.stock == 0 else f"{entry.stock} units available"
    response = f"SKU: {entry.sku} | Product: {entry.name} | Stock: {stock_status}"
    return FastPathResult(handled=True, response=response, tool_calls=1)


async def fast_path_detail_lookup(sku: str, context: ShopContext) -> FastPathResult:
    """Direct catalogue lookup for full details - NO LLM CALL."""
    result = catalogue_tool(CatalogueQuery(action="get", sku=sku))
    if not result.ok:
        return FastPathResult(
            handled=True,
            tool_calls=1,
            error=result.error.message if result.error else "Unknown error"
        )
    
    entry: CatalogueEntry = result.data
    lines = [
        f"SKU: {entry.sku}",
        f"Product: {entry.name}",
        f"Category: {entry.category}",
        f"Price: {context.currency} {entry.price:,}",
        f"Stock: {entry.stock} units",
    ]
    if entry.description:
        lines.append(f"Description: {entry.description}")
    if entry.weight_g:
        lines.append(f"Weight: {entry.weight_g}g")
    if entry.dimensions_cm:
        dims = entry.dimensions_cm
        lines.append(f"Dimensions: {dims.get('l', 0)}x{dims.get('w', 0)}x{dims.get('h', 0)} cm")
    if entry.tags:
        lines.append(f"Tags: {', '.join(entry.tags)}")
    
    response = "\n".join(lines)
    return FastPathResult(handled=True, response=response, tool_calls=1)


async def handle_fast_path_query(text: str, context: ShopContext) -> FastPathResult:
    """
    Main fast path handler.
    Returns FastPathResult with handled=True if query was answered without LLM.
    """
    intent = detect_intent(text)
    if not intent:
        return FastPathResult(handled=False)
    
    sku = extract_sku(text)
    if not sku:
        return FastPathResult(handled=False, error="No valid SKU found in query")
    
    if intent == "price":
        return await fast_path_price_lookup(sku, context)
    elif intent == "stock":
        return await fast_path_stock_check(sku, context)
    elif intent == "detail":
        return await fast_path_detail_lookup(sku, context)
    
    return FastPathResult(handled=False)