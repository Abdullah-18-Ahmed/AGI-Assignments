from __future__ import annotations

from datetime import datetime
from typing import Optional

from shop_desk.config.settings import get_settings
from shop_desk.models.shop import ShopContext, Tier


def is_within_operating_hours() -> bool:
    """Check if current time is within shop operating hours."""
    settings = get_settings()
    now = datetime.now()
    current_hour = now.hour
    return settings.shop_open_hour <= current_hour < settings.shop_close_hour


def get_next_opening_time() -> str:
    """Get formatted string for next opening time."""
    settings = get_settings()
    now = datetime.now()
    current_hour = now.hour
    
    if current_hour < settings.shop_open_hour:
        return f"today at {settings.shop_open_hour}:00"
    else:
        return f"tomorrow at {settings.shop_open_hour}:00"


def generate_fast_path_prompt(context: Optional[ShopContext] = None) -> str:
    """Generate system prompt for fast-path agents (price lookup, stock check, search)."""
    settings = get_settings()
    within_hours = is_within_operating_hours()
    next_open = get_next_opening_time()
    
    shop_name = context.shop if context else "Al-Noor Electronics"
    currency = context.currency if context else "PKR"
    tier = context.tier.value if context else "walk_in"
    
    hours_note = ""
    if not within_hours:
        hours_note = f"""
IMPORTANT: The shop is currently CLOSED (operating hours: {settings.shop_open_hour}:00-{settings.shop_close_hour}:00).
- Do NOT promise same-day delivery or pickup.
- Next opening: {next_open}.
- You may still provide price/stock information from catalogue.
"""
    
    return f"""You are a fast-path assistant for {shop_name} shop desk.
Currency: {currency}
Customer tier: {tier}
{hours_note}

RULES:
1. CATALOGUE ONLY: All prices, SKUs, stock levels MUST come from catalogue tool. Never generate/hallucinate.
2. EXACT VALUES: Prices quoted exactly as in catalogue ({currency}). Stock = exact integers.
3. NO GUESSING: If SKU not found, say "SKU not found" and offer search. Never invent prices.
4. CONCISE: Be direct. Use specified formats.
5. NO CUSTOMER DATA IN PROMPTS: Customer ID/tier provided via context only.

RESPONSE FORMATS:
- Price: "SKU: [sku] | Product: [name] | Price: {currency} [price]"
- Stock: "SKU: [sku] | Product: [name] | Stock: [stock] units" (or "out of stock")
- Search: Numbered list with SKU, name, price, stock, category
- Full Details: Multi-line with all catalogue fields

GUARDRAILS: Every response validated against catalogue before display. On mismatch, auto-corrected."""


def generate_reasoning_prompt(context: Optional[ShopContext] = None) -> str:
    """Generate system prompt for reasoning agent (comparisons, recommendations)."""
    settings = get_settings()
    within_hours = is_within_operating_hours()
    next_open = get_next_opening_time()
    
    shop_name = context.shop if context else "Al-Noor Electronics"
    currency = context.currency if context else "PKR"
    tier = context.tier.value if context else "walk_in"
    
    hours_note = ""
    if not within_hours:
        hours_note = f"""
IMPORTANT: The shop is currently CLOSED (operating hours: {settings.shop_open_hour}:00-{settings.shop_close_hour}:00).
- Do NOT promise same-day delivery, pickup, or immediate fulfillment.
- Next opening: {next_open}.
- You may still analyze and compare products from catalogue.
"""
    
    return f"""You are the reasoning agent for {shop_name} shop desk.
Currency: {currency}
Customer tier: {tier}
{hours_note}

RULES:
1. CATALOGUE ONLY: All product data MUST come from catalogue tool. Never generate/hallucinate.
2. EXACT VALUES: Prices exactly as in catalogue ({currency}). Stock = exact integers.
3. STRUCTURED ANALYSIS: Comparisons in clear tables. Reference catalogue for all claims.
4. NO CUSTOMER DATA IN PROMPTS: Customer ID/tier via context only.
5. NO PROMISES OUTSIDE HOURS: {hours_note.strip() if not within_hours else "Normal operations."}

CAPABILITIES:
- Multi-product price comparisons (2-5 SKUs)
- Product recommendations based on stated needs
- Complex queries requiring reasoning across products
- Low-stock alerts and inventory analysis

COMPARISON FORMAT:
| SKU | Product | Price ({currency}) | Stock | Category |
|-----|---------|-------------------|-------|----------|
| ... | ...     | ...               | ...   | ...      """

def get_operating_hours_status() -> dict:
    """Get current operating hours status for use in responses."""
    settings = get_settings()
    now = datetime.now()
    within_hours = is_within_operating_hours()
    next_open = get_next_opening_time()
    
    return {
        "is_open": within_hours,
        "current_hour": now.hour,
        "open_hour": settings.shop_open_hour,
        "close_hour": settings.shop_close_hour,
        "next_opening": next_open,
        "message": f"Shop is {'open' if within_hours else 'closed'}. "
                   f"Operating hours: {settings.shop_open_hour}:00-{settings.shop_close_hour}:00. "
                   f"Next opening: {next_open}."
    }