from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from shop_desk.agents.base import BaseAgent, Path
from shop_desk.models.shop import (
    LineItem,
    Order,
    ShopContext,
    ToolError,
    ToolResult,
)
from shop_desk.tools import catalogue_tool, CatalogueQuery
from shop_desk.guardrails import validate_order_items, validate_response, get_polite_refusal


class QuoteInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[dict] = Field(..., description="List of {sku, quantity} dicts")
    tax_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    shipping_flat: int = Field(default=0, ge=0)


class OrderConfirmInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str
    confirmed: bool


SYSTEM_PROMPT = """You are the Quote Agent for Al-Noor Electronics shop desk.
You create price quotes and order summaries from catalogue data.

RULES:
1. ALL PRICES FROM CATALOGUE: Use catalogue_tool.multi_get to fetch exact prices
2. COMPUTE TOTALS IN PYTHON: Line totals, subtotal, tax, shipping, grand total computed in code
3. NEVER LET LLM COMPUTE TOTALS: The LLM only formats the response, Python does the math
4. VALIDATE STOCK: Check availability before quoting
5. GUARDRAIL OUTPUT: Every response validated against catalogue before display

RESPONSE FORMAT FOR QUOTE:
Order Quote:
1. SKU: [sku] | [name] | Qty: [qty] | Unit: PKR [price] | Line: PKR [line_total]
...
Subtotal: PKR [subtotal]
Tax: PKR [tax]
Shipping: PKR [shipping]
Grand Total: PKR [grand_total]

Order ID: [order_id] (DRAFT - confirm to finalize)"""


class QuoteAgent(BaseAgent[QuoteInput]):
    def __init__(self, model: str | None = None):
        super().__init__(
            name="QuoteAgent",
            path=Path.FAST,
            model=model,
            use_dynamic_prompt=True,
        )

    async def run(self, input_data: QuoteInput, context: ShopContext) -> ToolResult:
        # Validate items against catalogue
        valid, violations = validate_order_items(input_data.items)
        if not valid:
            return ToolResult.failure("VALIDATION_ERROR", "; ".join(violations))

        # Fetch catalogue entries for all SKUs
        skus = [item["sku"].upper() for item in input_data.items]
        cat_result = catalogue_tool(CatalogueQuery(action="multi_get", skus=skus))
        if not cat_result.ok:
            return ToolResult.failure(cat_result.error.code, cat_result.error.message)

        entries = {e.sku: e for e in cat_result.data}
        
        # Build line items with catalogue prices
        line_items = []
        for item in input_data.items:
            sku = item["sku"].upper()
            qty = item["quantity"]
            entry = entries[sku]
            
            line_item = LineItem(
                sku=entry.sku,
                name=entry.name,
                unit_price=entry.price,
                quantity=qty,
                line_total=entry.price * qty,
            )
            line_items.append(line_item)

        # Compute totals in Python (not LLM)
        tax = int(sum(li.line_total for li in line_items) * input_data.tax_rate)
        shipping = input_data.shipping_flat
        
        order = Order.create_from_items(
            items=line_items,
            tax=tax,
            shipping=shipping,
            currency=context.currency,
        )

        # Format response
        lines = ["Order Quote:"]
        for i, li in enumerate(line_items, 1):
            lines.append(
                f"{i}. SKU: {li.sku} | {li.name} | Qty: {li.quantity} | "
                f"Unit: {context.currency} {li.unit_price:,} | Line: {context.currency} {li.line_total:,}"
            )
        lines.append("")
        lines.append(f"Subtotal: {context.currency} {order.subtotal:,}")
        lines.append(f"Tax: {context.currency} {order.tax:,}")
        lines.append(f"Shipping: {context.currency} {order.shipping:,}")
        lines.append(f"Grand Total: {context.currency} {order.grand_total:,}")
        lines.append("")
        lines.append(f"Order ID: {order.order_id} (DRAFT - confirm to finalize)")

        response = "\n".join(lines)
        
        # Guardrail check on output
        guardrail_result = validate_response(response)
        if not guardrail_result.passed:
            # Return corrected version
            if guardrail_result.corrected_response:
                return ToolResult.success(guardrail_result.corrected_response)
            else:
                return ToolResult.failure("GUARDRAIL_VIOLATION", 
                    get_polite_refusal(guardrail_result.violations))

        return ToolResult.success(response)


class OrderConfirmAgent(BaseAgent[OrderConfirmInput]):
    def __init__(self, model: str | None = None):
        super().__init__(
            name="OrderConfirmAgent",
            path=Path.FAST,
            model=model,
            use_dynamic_prompt=True,
        )

    async def run(self, input_data: OrderConfirmInput, context: ShopContext) -> ToolResult:
        # In a real implementation, you'd retrieve the draft order from session storage
        # For now, return a confirmation message
        if input_data.confirmed:
            response = f"Order {input_data.order_id} confirmed. Thank you for your order!"
        else:
            response = f"Order {input_data.order_id} cancelled."
        
        guardrail_result = validate_response(response)
        if not guardrail_result.passed:
            if guardrail_result.corrected_response:
                return ToolResult.success(guardrail_result.corrected_response)
            return ToolResult.failure("GUARDRAIL_VIOLATION",
                get_polite_refusal(guardrail_result.violations))
        
        return ToolResult.success(response)


async def handle_quote(items: list[dict], context: ShopContext, 
                       tax_rate: float = 0.0, shipping_flat: int = 0,
                       model: str | None = None) -> ToolResult:
    agent = QuoteAgent(model=model)
    return await agent.run(QuoteInput(items=items, tax_rate=tax_rate, shipping_flat=shipping_flat), context)


async def handle_order_confirm(order_id: str, confirmed: bool, context: ShopContext,
                                model: str | None = None) -> ToolResult:
    agent = OrderConfirmAgent(model=model)
    return await agent.run(OrderConfirmInput(order_id=order_id, confirmed=confirmed), context)