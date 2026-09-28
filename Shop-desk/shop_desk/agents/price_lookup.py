from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from shop_desk.agents.base import BaseAgent, Path
from shop_desk.models.shop import (
    CatalogueEntry,
    ShopContext,
    ToolError,
    ToolResult,
)
from shop_desk.tools import catalogue_tool, CatalogueQuery


class PriceLookupInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str = Field(..., description="Product SKU to look up")


class StockCheckInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str = Field(..., description="Product SKU to check stock for")


class DetailLookupInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str = Field(..., description="Product SKU to get full details for")


class PriceLookupAgent(BaseAgent[PriceLookupInput]):
    def __init__(self, model: str | None = None):
        super().__init__(
            name="PriceLookupAgent",
            path=Path.FAST,
            model=model,
            use_dynamic_prompt=True,
        )

    async def run(self, input_data: PriceLookupInput, context: ShopContext) -> ToolResult:
        result = catalogue_tool(CatalogueQuery(action="get", sku=input_data.sku))
        if not result.ok:
            return ToolResult.failure(result.error.code, result.error.message)

        entry: CatalogueEntry = result.data
        response = f"SKU: {entry.sku} | Product: {entry.name} | Price: {context.currency} {entry.price:,}"
        return ToolResult.success(response)


class StockCheckAgent(BaseAgent[StockCheckInput]):
    def __init__(self, model: str | None = None):
        super().__init__(
            name="StockCheckAgent",
            path=Path.FAST,
            model=model,
            use_dynamic_prompt=True,
        )

    async def run(self, input_data: StockCheckInput, context: ShopContext) -> ToolResult:
        result = catalogue_tool(CatalogueQuery(action="get", sku=input_data.sku))
        if not result.ok:
            return ToolResult.failure(result.error.code, result.error.message)

        entry: CatalogueEntry = result.data
        stock_status = "out of stock" if entry.stock == 0 else f"{entry.stock} units available"
        response = f"SKU: {entry.sku} | Product: {entry.name} | Stock: {stock_status}"
        return ToolResult.success(response)


class DetailLookupAgent(BaseAgent[DetailLookupInput]):
    def __init__(self, model: str | None = None):
        super().__init__(
            name="DetailLookupAgent",
            path=Path.FAST,
            model=model,
            use_dynamic_prompt=True,
        )

    async def run(self, input_data: DetailLookupInput, context: ShopContext) -> ToolResult:
        result = catalogue_tool(CatalogueQuery(action="get", sku=input_data.sku))
        if not result.ok:
            return ToolResult.failure(result.error.code, result.error.message)

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
        return ToolResult.success(response)


async def handle_price_lookup(sku: str, context: ShopContext, model: str | None = None) -> ToolResult:
    agent = PriceLookupAgent(model=model)
    return await agent.run(PriceLookupInput(sku=sku), context)


async def handle_stock_check(sku: str, context: ShopContext, model: str | None = None) -> ToolResult:
    agent = StockCheckAgent(model=model)
    return await agent.run(StockCheckInput(sku=sku), context)


async def handle_detail_lookup(sku: str, context: ShopContext, model: str | None = None) -> ToolResult:
    agent = DetailLookupAgent(model=model)
    return await agent.run(DetailLookupInput(sku=sku), context)