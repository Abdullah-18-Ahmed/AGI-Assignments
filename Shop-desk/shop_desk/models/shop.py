from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Generic, List, Optional, TypeVar
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
import uuid


class Path(str, Enum):
    FAST = "fast"
    REASONING = "reasoning"


class Tier(str, Enum):
    WALK_IN = "walk_in"
    REGULAR = "regular"


class EscalationReason(str, Enum):
    OUT_OF_STOCK = "out_of_stock"
    DISPUTE = "dispute"
    TURN_LIMIT_REACHED = "turn_limit_reached"
    UNKNOWN = "unknown"


class OrderStatus(str, Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class ShopContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False)

    shop: str = "Al-Noor Electronics"
    currency: str = "PKR"
    customer_id: Optional[str] = None
    tier: Tier = Tier.WALK_IN
    session_id: str
    turn_count: int = 0
    catalogue_version: str = "1.0.0"
    history: List[HistoryEntry] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class CatalogueEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str
    name: str
    category: str
    price: int
    stock: int
    description: str = ""
    weight_g: Optional[int] = None
    dimensions_cm: Optional[dict[str, int]] = None
    tags: list[str] = Field(default_factory=list)


class LineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str
    name: str
    unit_price: int
    quantity: int = Field(ge=1)
    line_total: int

    @model_validator(mode="after")
    def validate_line_total(self) -> "LineItem":
        expected = self.unit_price * self.quantity
        if self.line_total != expected:
            raise ValueError(f"line_total {self.line_total} != unit_price * quantity ({expected})")
        return self


class Order(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str = Field(default_factory=lambda: f"ORD-{uuid.uuid4().hex[:8].upper()}")
    status: OrderStatus = OrderStatus.DRAFT
    items: list[LineItem]
    subtotal: int
    tax: int
    shipping: int
    grand_total: int
    currency: str = "PKR"
    created_at: datetime = Field(default_factory=datetime.now)

    @model_validator(mode="after")
    def validate_totals(self) -> "Order":
        computed_subtotal = sum(item.line_total for item in self.items)
        if self.subtotal != computed_subtotal:
            raise ValueError(f"subtotal {self.subtotal} != computed sum of line_totals ({computed_subtotal})")
        
        computed_grand = self.subtotal + self.tax + self.shipping
        if self.grand_total != computed_grand:
            raise ValueError(f"grand_total {self.grand_total} != subtotal + tax + shipping ({computed_grand})")
        return self

    @classmethod
    def create_from_items(
        cls,
        items: list[LineItem],
        tax: int = 0,
        shipping: int = 0,
        currency: str = "PKR",
    ) -> "Order":
        subtotal = sum(item.line_total for item in items)
        grand_total = subtotal + tax + shipping
        return cls(
            items=items,
            subtotal=subtotal,
            tax=tax,
            shipping=shipping,
            grand_total=grand_total,
            currency=currency,
        )


class SearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str
    name: str
    price: int
    stock: int
    category: str
    relevance_score: float


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    model: str


class HistoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str
    content: str
    path: Optional[Path] = None
    tokens: Optional[TokenUsage] = None
    timestamp: float


T = TypeVar("T")


class ToolError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class ToolResult(BaseModel, Generic[T]):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    data: Optional[T] = None
    error: Optional[ToolError] = None

    @classmethod
    def success(cls, data: T) -> ToolResult[T]:
        return cls(ok=True, data=data)

    @classmethod
    def failure(cls, code: str, message: str) -> ToolResult[T]:
        return cls(ok=False, error=ToolError(code=code, message=message))


class TraceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str
    path: Path
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    turn_count: int
    agent: str
    timestamp: float


class SessionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    total_turns: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    model_distribution: dict[str, int]
    path_distribution: dict[str, int]


class TurnCost(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_number: int
    agent: str
    model: str
    path: Path
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    prompt_cost_usd: float
    completion_cost_usd: float
    total_cost_usd: float
    timestamp: float


class RunCostSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    total_turns: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    total_cost_usd: float
    fast_path_turns: int
    fast_path_cost_usd: float
    reasoning_path_turns: int
    reasoning_path_cost_usd: float
    model_breakdown: dict[str, dict[str, float]]
    turns: list[TurnCost]


class EscalationHandoff(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    reason: EscalationReason
    summary: str
    filtered_history: list[HistoryEntry]
    original_turn_count: int
    filtered_turn_count: int
    cost_summary: RunCostSummary
    timestamp: float


class LifecycleEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: str
    session_id: str
    turn_number: int
    agent: str
    model: str
    path: Path
    timestamp: float
    metadata: dict = Field(default_factory=dict)