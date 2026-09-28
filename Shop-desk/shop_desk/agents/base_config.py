from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Generic, Optional, TypeVar
from copy import deepcopy

from pydantic import BaseModel, ConfigDict

from shop_desk.models.shop import ShopContext, ToolError, ToolResult, Path, EscalationReason


T = TypeVar("T", bound=BaseModel)
R = TypeVar("R")


@dataclass
class AgentTool:
    """Represents a tool that an agent can use."""
    name: str
    description: str
    func: Callable
    parameters_schema: dict
    tier_required: str = "walk_in"  # "walk_in" or "regular"
    seasonal: bool = False  # If True, tool is disabled by default


@dataclass
class BaseAgentConfig:
    """Base configuration for all agents. Can be cloned and customized."""
    name: str
    model: str
    path: Path
    instructions: str
    tools: list[AgentTool] = field(default_factory=list)
    max_turns: int = 10
    temperature: float = 0.1
    
    def clone(
        self,
        name: Optional[str] = None,
        model: Optional[str] = None,
        instructions: Optional[str] = None,
        tools: Optional[list[AgentTool]] = None,
        max_turns: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> "BaseAgentConfig":
        """Create a copy of this config with optional overrides."""
        return BaseAgentConfig(
            name=name or self.name,
            model=model or self.model,
            path=self.path,
            instructions=instructions or self.instructions,
            tools=deepcopy(tools) if tools is not None else deepcopy(self.tools),
            max_turns=max_turns if max_turns is not None else self.max_turns,
            temperature=temperature if temperature is not None else self.temperature,
        )
    
    def with_tools(self, *tools: AgentTool) -> "BaseAgentConfig":
        """Return a new config with additional tools."""
        new_config = self.clone()
        new_config.tools.extend(tools)
        return new_config
    
    def without_tools(self, *tool_names: str) -> "BaseAgentConfig":
        """Return a new config without specified tools."""
        new_config = self.clone()
        new_config.tools = [t for t in new_config.tools if t.name not in tool_names]
        return new_config
    
    def filter_tools_by_tier(self, tier: str) -> list[AgentTool]:
        """Return tools available for the given tier."""
        return [
            t for t in self.tools 
            if not t.seasonal and (t.tier_required == "walk_in" or tier == "regular")
        ]


class BaseAgent(ABC, Generic[T]):
    """Base agent class with configuration-driven behavior."""
    
    def __init__(self, config: BaseAgentConfig):
        self.config = config
        self._turn_count = 0
    
    @property
    def name(self) -> str:
        return self.config.name
    
    @property
    def model(self) -> str:
        return self.config.model
    
    @property
    def max_turns(self) -> int:
        return self.config.max_turns
    
    @abstractmethod
    async def run(self, input_data: T, context: ShopContext) -> ToolResult:
        pass
    
    def _check_turn_limit(self, context: ShopContext) -> bool:
        """Check if turn limit has been reached."""
        return context.turn_count >= self.config.max_turns
    
    def _get_polite_fallback(self, context: ShopContext) -> str:
        """Generate polite fallback message when turn limit reached."""
        return (
            f"I've reached the maximum number of steps for this inquiry. "
            f"Let me connect you with a specialist or you can try rephrasing your question. "
            f"(Turn limit: {self.config.max_turns})"
        )
    
    def get_available_tools(self, context: ShopContext) -> list[AgentTool]:
        """Get tools available for the current context tier."""
        return self.config.filter_tools_by_tier(context.tier.value)


# Tool input/output models
class PricingQuery(BaseModel):
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


class EscalationQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)
    
    reason: "EscalationReason"
    customer_tier: str
    conversation_summary: str


class EscalationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    
    escalated: bool
    case_id: str
    message: str
    estimated_response_time: str


# Rebuild model after EscalationReason is available
try:
    EscalationQuery.model_rebuild()
except Exception:
    pass  # Will be rebuilt when first used