from __future__ import annotations

import time
from typing import Optional

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict

from shop_desk.config.settings import get_settings
from shop_desk.models.shop import (
    Path,
    ShopContext,
    ToolError,
    ToolResult,
    TokenUsage,
    TraceEntry,
    EscalationReason,
    EscalationHandoff,
    HistoryEntry,
)
from shop_desk.tools import trace_tool, TraceQuery
from shop_desk.agents.base_config import (
    BaseAgent,
    BaseAgentConfig,
    AgentTool,
    PricingQuery,
    PricingResult,
    EscalationQuery,
    EscalationResult,
)
from shop_desk.tools import catalogue_tool, CatalogueQuery
from shop_desk.guardrails import validate_response, validate_order_items
from shop_desk.cost import get_lifecycle_manager, LifecycleManager, LifecycleHook


def make_catalogue_tool() -> AgentTool:
    """Create the catalogue lookup tool."""
    return AgentTool(
        name="catalogue_lookup",
        description="Look up product details from catalogue by SKU",
        func=lambda sku: catalogue_tool(CatalogueQuery(action="get", sku=sku)),
        parameters_schema={
            "type": "object",
            "properties": {
                "sku": {"type": "string", "description": "Product SKU"}
            },
            "required": ["sku"]
        },
        tier_required="walk_in",
    )


def make_multi_catalogue_tool() -> AgentTool:
    """Create the multi-SKU catalogue lookup tool."""
    return AgentTool(
        name="multi_catalogue_lookup",
        description="Look up multiple products from catalogue",
        func=lambda skus: catalogue_tool(CatalogueQuery(action="multi_get", skus=skus)),
        parameters_schema={
            "type": "object",
            "properties": {
                "skus": {"type": "array", "items": {"type": "string"}, "description": "List of SKUs"}
            },
            "required": ["skus"]
        },
        tier_required="walk_in",
    )


def make_validate_order_tool() -> AgentTool:
    """Create the order validation tool (regular tier only)."""
    return AgentTool(
        name="validate_order",
        description="Validate order items against catalogue (regular tier only)",
        func=lambda items: validate_order_items(items),
        parameters_schema={
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "sku": {"type": "string"},
                            "quantity": {"type": "integer"},
                            "unit_price": {"type": "integer"}
                        },
                        "required": ["sku", "quantity"]
                    }
                }
            },
            "required": ["items"]
        },
        tier_required="regular",
    )


# Base configuration for all specialists
BASE_SPECIALIST_CONFIG = BaseAgentConfig(
    name="BaseSpecialist",
    model="openai/gpt-4o-mini",
    path=Path.FAST,
    instructions="You are a specialist agent for Al-Noor Electronics shop desk.",
    tools=[
        make_catalogue_tool(),
        make_multi_catalogue_tool(),
        make_validate_order_tool(),
    ],
    max_turns=5,
)


# Pricing Specialist - uses gpt-4o, higher turn budget
PRICING_SPECIALIST_CONFIG = BASE_SPECIALIST_CONFIG.clone(
    name="PricingSpecialist",
    model="openai/gpt-4o",
    instructions="""You are the Pricing Specialist for Al-Noor Electronics.
    
Your role: Provide EXACT numerical pricing calculations for orders.
- Use catalogue_lookup or multi_catalogue_lookup to get EXACT prices from catalogue
- Compute line totals, subtotals, tax, shipping in Python (not LLM)
- Return structured PricingResult with exact integers
- Never estimate or round prices
- If validation fails, return error with exact reason

TOOLS: catalogue_lookup, multi_catalogue_lookup, validate_order (regular tier only)
OUTPUT: Exact numerical values only""",
    max_turns=15,  # Higher turn budget for complex pricing
)


# Escalation Specialist - uses gpt-4o-mini, standard turn budget
ESCALATION_SPECIALIST_CONFIG = BASE_SPECIALIST_CONFIG.clone(
    name="EscalationSpecialist",
    model="openai/gpt-4o-mini",
    instructions="""You are the Escalation Specialist for Al-Noor Electronics.
    
Your role: Handle complex customer issues requiring human intervention.
- Analyze conversation summary and reason for escalation
- Generate case ID and estimated response time
- Be empathetic but professional
- Do NOT make pricing calculations - that's for Pricing Specialist

TOOLS: None (escalation doesn't need catalogue)
OUTPUT: Structured escalation result""",
    max_turns=5,
    tools=[],  # No catalogue tools needed for escalation
)


class PricingSpecialistAgent(BaseAgent[PricingQuery]):
    """Pricing Specialist: Exact numerical pricing with turn budget."""
    
    def __init__(self, config: Optional[BaseAgentConfig] = None):
        super().__init__(config or PRICING_SPECIALIST_CONFIG)
        self._client: Optional[AsyncOpenAI] = None
    
    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            settings = get_settings()
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._client
    
    async def run(self, input_data: PricingQuery, context: ShopContext) -> ToolResult:
        # Check turn limit
        if self._check_turn_limit(context):
            return ToolResult.failure(
                "TURN_LIMIT_EXCEEDED",
                self._get_polite_fallback(context)
            )
        
        # Validate SKU exists
        cat_result = catalogue_tool(CatalogueQuery(action="get", sku=input_data.sku))
        if not cat_result.ok:
            return ToolResult.failure(cat_result.error.code, cat_result.error.message)
        
        entry = cat_result.data
        
        # Compute exact pricing
        line_total = entry.price * input_data.quantity
        tax = 0
        shipping = 0
        
        if input_data.include_tax:
            tax = int(line_total * 0.18)  # 18% tax
        if input_data.include_shipping:
            shipping = 500 if line_total < 50000 else 0  # Free shipping over 50k
        
        grand_total = line_total + tax + shipping
        
        result = PricingResult(
            sku=entry.sku,
            name=entry.name,
            unit_price=entry.price,
            quantity=input_data.quantity,
            line_total=line_total,
            tax=tax,
            shipping=shipping,
            grand_total=grand_total,
        )
        
        # Log trace
        trace_tool(TraceQuery(action="log", entry=TraceEntry(
            model=self.config.model,
            path=self.config.path,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            turn_count=1,
            agent=self.name,
            timestamp=time.time(),
        )))
        
        return ToolResult.success(result)


class EscalationSpecialistAgent(BaseAgent[EscalationQuery]):
    """Escalation Specialist: Handle complex issues requiring human review."""
    
    def __init__(self, config: Optional[BaseAgentConfig] = None):
        super().__init__(config or ESCALATION_SPECIALIST_CONFIG)
        self._client: Optional[AsyncOpenAI] = None
    
    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            settings = get_settings()
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._client
    
    async def run(self, input_data: EscalationQuery, context: ShopContext) -> ToolResult:
        if self._check_turn_limit(context):
            return ToolResult.failure(
                "TURN_LIMIT_EXCEEDED",
                self._get_polite_fallback(context)
            )
        
        # Generate case ID
        import uuid
        case_id = f"ESC-{uuid.uuid4().hex[:8].upper()}"
        
        # Determine response time based on tier
        if input_data.customer_tier == "regular":
            est_time = "2 hours"
        else:
            est_time = "24 hours"
        
        result = EscalationResult(
            escalated=True,
            case_id=case_id,
            message=(
                f"Your issue has been escalated. Case ID: {case_id}. "
                f"A specialist will review your case: {input_data.reason}. "
                f"Estimated response: {est_time}."
            ),
            estimated_response_time=est_time,
        )
        
        trace_tool(TraceQuery(action="log", entry=TraceEntry(
            model=self.config.model,
            path=self.config.path,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            turn_count=1,
            agent=self.name,
            timestamp=time.time(),
        )))
        
        return ToolResult.success(result)


# Agent tool wrappers for Desk agent to use
class PricingSpecialistTool:
    """Tool wrapper exposing Pricing Specialist as a function tool."""
    
    def __init__(self, agent: Optional[PricingSpecialistAgent] = None):
        self.agent = agent or PricingSpecialistAgent()
    
    async def __call__(self, query: PricingQuery, context: ShopContext) -> PricingResult:
        result = await self.agent.run(query, context)
        if not result.ok:
            raise ValueError(result.error.message)
        return result.data


class EscalationSpecialistTool:
    """Tool wrapper exposing Escalation Specialist as a function tool."""
    
    def __init__(self, agent: Optional[EscalationSpecialistAgent] = None):
        self.agent = agent or EscalationSpecialistAgent()
    
    async def __call__(self, query: EscalationQuery, context: ShopContext) -> EscalationResult:
        result = await self.agent.run(query, context)
        if not result.ok:
            raise ValueError(result.error.message)
        return result.data


# Default instances
pricing_specialist = PricingSpecialistAgent()
escalation_specialist = EscalationSpecialistAgent()
pricing_specialist_tool = PricingSpecialistTool(pricing_specialist)
escalation_specialist_tool = EscalationSpecialistTool(escalation_specialist)


async def handle_pricing_query(
    sku: str, 
    context: ShopContext, 
    quantity: int = 1,
    include_tax: bool = False,
    include_shipping: bool = False,
) -> ToolResult:
    """Handle pricing query via Pricing Specialist."""
    query = PricingQuery(
        sku=sku,
        quantity=quantity,
        include_tax=include_tax,
        include_shipping=include_shipping,
    )
    return await pricing_specialist.run(query, context)


async def handle_escalation(
    reason: EscalationReason,
    context: ShopContext,
    conversation_summary: str = "",
    history: Optional[list[HistoryEntry]] = None,
) -> ToolResult:
    """Handle escalation via Escalation Specialist."""
    query = EscalationQuery(
        reason=reason,
        customer_tier=context.tier.value,
        conversation_summary=conversation_summary,
    )
    return await escalation_specialist.run(query, context)


async def create_escalation_handoff(
    reason: EscalationReason,
    context: ShopContext,
    summary: str,
    history: list[HistoryEntry],
    lifecycle_manager: Optional[LifecycleManager] = None,
) -> EscalationHandoff:
    """Create a full escalation handoff with filtered history and cost summary."""
    lm = lifecycle_manager or get_lifecycle_manager()
    return lm.handoff(
        session_id=context.session_id,
        reason=reason,
        summary=summary,
        history=history,
        context=context,
    )