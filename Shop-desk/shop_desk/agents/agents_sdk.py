from __future__ import annotations

from agents import Agent, function_tool, RunContextWrapper, Runner, handoff
from agents.extensions.handoff_prompt import RECOMMENDED_PROMPT_PREFIX
from pydantic import BaseModel, ConfigDict
from typing import Optional, List

from shop_desk.config.settings import get_settings
from shop_desk.models.shop import (
    ShopContext,
    CatalogueEntry,
    SearchResult,
    LineItem,
    Order,
    EscalationReason,
    EscalationHandoff,
    Path,
    Tier,
    HistoryEntry,
)
from shop_desk.tools.catalogue import catalogue_tool, CatalogueQuery
from shop_desk.history import get_history_manager, reset_history_manager
from shop_desk.cost import get_lifecycle_manager


# Tool: Catalogue Lookup
@function_tool
async def catalogue_lookup(
    ctx: RunContextWrapper[ShopContext],
    sku: str,
) -> CatalogueEntry:
    """Look up a single product by SKU from the catalogue."""
    result = catalogue_tool(CatalogueQuery(action="get", sku=sku))
    if not result.ok:
        raise ValueError(result.error.message)
    return result.data


@function_tool
async def multi_catalogue_lookup(
    ctx: RunContextWrapper[ShopContext],
    skus: List[str],
) -> List[CatalogueEntry]:
    """Look up multiple products by SKU from the catalogue."""
    result = catalogue_tool(CatalogueQuery(action="multi_get", skus=skus))
    if not result.ok:
        raise ValueError(result.error.message)
    return result.data


@function_tool
async def catalogue_search(
    ctx: RunContextWrapper[ShopContext],
    query: str,
    page: int = 1,
    page_size: int = 10,
) -> List[SearchResult]:
    """Search products by keyword."""
    result = catalogue_tool(CatalogueQuery(action="search", query=query, page=page, page_size=page_size))
    if not result.ok:
        raise ValueError(result.error.message)
    return result.data


@function_tool
async def catalogue_category(
    ctx: RunContextWrapper[ShopContext],
    category: str,
    page: int = 1,
    page_size: int = 20,
) -> List[SearchResult]:
    """Browse products by category."""
    result = catalogue_tool(CatalogueQuery(action="category", category=category, page=page, page_size=page_size))
    if not result.ok:
        raise ValueError(result.error.message)
    return result.data


# Handoff input - passed when escalation is triggered
class EscalationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: EscalationReason
    summary: str


# Handoff callback - runs when escalation is triggered
async def on_escalation_handoff(
    ctx: RunContextWrapper[ShopContext],
    input_data: EscalationInput,
) -> None:
    """Handle escalation handoff - create summary and filtered history for human."""
    lm = get_lifecycle_manager()
    history_manager = get_history_manager(ctx.context)
    
    # Filter history for human handoff
    filtered_history = lm._filter_history_for_handoff(ctx.context.history)
    
    # Create handoff record with cost summary
    lm.handoff(
        session_id=ctx.context.session_id,
        reason=input_data.reason,
        summary=input_data.summary,
        history=ctx.context.history,
        context=ctx.context,
    )
    
    # Store filtered history in context for the escalation specialist to use
    ctx.context.metadata = getattr(ctx.context, 'metadata', {})
    ctx.context.metadata['filtered_history'] = filtered_history
    ctx.context.metadata['escalation_summary'] = input_data.summary
    ctx.context.metadata['escalation_reason'] = input_data.reason


# Escalation Specialist Agent - receives filtered history via context
escalation_specialist = Agent[ShopContext](
    name="EscalationSpecialist",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
You are the Escalation Specialist for Al-Noor Electronics. You handle complex issues that need human attention.

When a customer is escalated to you:
1. Acknowledge their concern empathetically
2. The filtered conversation history and summary are available in your context
3. Generate a case ID (format: ESC-XXXXXXXX)
4. Give them a clear timeline based on their tier:
   - Walk-in: 24 hours
   - Regular: 2 hours
4. Provide a brief summary of their issue so they don't have to repeat themselves
5. Reassure them their issue is being taken seriously

You have access to the filtered conversation history and a summary of the issue.
Speak naturally and warmly. Don't use bullet points or structured formats unless asked.
""",
    model="openai/gpt-4o-mini",
    tools=[],
    handoffs=[],
)


# Pricing Specialist Agent
class PricingInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: str
    quantity: int = 1
    include_tax: bool = False
    include_shipping: bool = False


class PricingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sku: str
    name: str
    unit_price: int
    quantity: int
    line_total: int
    tax: int = 0
    shipping: int = 0
    grand_total: int


@function_tool
async def calculate_pricing(
    ctx: RunContextWrapper[ShopContext],
    input: PricingInput,
) -> PricingResult:
    """Calculate exact pricing for an order."""
    cat_result = catalogue_tool(CatalogueQuery(action="get", sku=input.sku))
    if not cat_result.ok:
        raise ValueError(cat_result.error.message)
    
    entry = cat_result.data
    line_total = entry.price * input.quantity
    tax = int(line_total * 0.18) if input.include_tax else 0
    shipping = 500 if input.include_shipping and line_total < 50000 else 0
    grand_total = line_total + tax + shipping
    
    return PricingResult(
        sku=entry.sku,
        name=entry.name,
        unit_price=entry.price,
        quantity=input.quantity,
        line_total=line_total,
        tax=tax,
        shipping=shipping,
        grand_total=grand_total,
    )


pricing_specialist = Agent[ShopContext](
    name="PricingSpecialist",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
You are the Pricing Specialist at Al-Noor Electronics. You provide exact, detailed quotes.

When giving pricing:
- Use catalogue_lookup to get exact prices
- Calculate everything precisely (no rounding)
- Present the breakdown naturally in conversation
- Include tax (18%) and shipping (500 PKR under 50k, free over 50k) when asked
- If an item is out of stock, mention it clearly

Keep responses conversational. Use the structured PricingResult tool for calculations, 
but present the final answer in a natural, friendly way.
""",
    model="openai/gpt-4o",
    tools=[catalogue_lookup, multi_catalogue_lookup, calculate_pricing],
    handoffs=[handoff(escalation_specialist)],
)


# Main Desk Agent
desk_agent = Agent[ShopContext](
    name="ShopDeskAgent",
    instructions=f"""{RECOMMENDED_PROMPT_PREFIX}
You are the friendly shop assistant at Al-Noor Electronics. You help customers naturally — 
like a real person at a shop counter would.

Your personality:
- Warm, helpful, conversational
- Use natural language, not bullet points or structured lists
- Ask follow-up questions when needed
- Remember what they've asked about earlier

Tools you have:
- catalogue_lookup: Check price, stock, or details for a specific SKU
- catalogue_search: Find products by keyword (e.g., "blender", "kitchen")
- catalogue_category: Browse by category (kitchen, cooling, laundry, etc.)
- multi_catalogue_lookup: Get multiple products at once

When to handoff:
- Customer asks for a quote with quantities and tax/shipping → FIRST search for the products by name, THEN handoff to PricingSpecialist with the SKUs and quantities
- Customer wants to escalate/dispute → EscalationSpecialist (use the handoff with reason and summary)
- Customer mentions turn limits → EscalationSpecialist

Response style:
- One or two short paragraphs max
- No markdown tables, no structured lists unless asked
- Use rupees symbol (₨) or PKR naturally
- Reference previous items in conversation by name, not SKU

When a customer asks for a quote like "2 kettles and 1 blender with tax":
1. First use catalogue_search for "kettle" to find the kettle SKU
2. Then use catalogue_search for "blender" to find the blender SKU  
3. Then handoff to PricingSpecialist with the SKUs, quantities, and tax/shipping requirements
""",
    model="openai/gpt-4o-mini",
    tools=[
        catalogue_lookup,
        multi_catalogue_lookup,
        catalogue_search,
        catalogue_category,
    ],
    handoffs=[
        handoff(pricing_specialist),
        handoff(
            agent=escalation_specialist,
            on_handoff=on_escalation_handoff,
            input_type=EscalationInput,
        ),
    ],
)


# Build conversation history for the agent
def build_conversation_input(context: ShopContext, user_message: str) -> List[dict]:
    """Build the full conversation history for the agent including history."""
    messages = []
    
    # Add conversation history
    for entry in context.history:
        if entry.role in ("user", "assistant"):
            messages.append({"role": entry.role, "content": entry.content})
    
    # Add current user message
    messages.append({"role": "user", "content": user_message})
    
    return messages


# Convenience function to run the desk agent
async def run_desk_agent(
    user_message: str,
    context: ShopContext,
) -> str:
    """Run the desk agent with user message and context."""
    history_manager = get_history_manager(context)
    history_manager.add_user_message(user_message)
    
    # Build full conversation including history
    conversation_input = build_conversation_input(context, user_message)
    
    # Run agent with full conversation history
    result = await Runner.run(
        desk_agent,
        input=conversation_input,
        context=context,
    )
    
    history_manager.add_assistant_message(result.final_output, path="fast")
    return result.final_output