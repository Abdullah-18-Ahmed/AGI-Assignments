from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from shop_desk.agents.base import BaseAgent, Path
from shop_desk.models.shop import (
    SearchResult,
    ShopContext,
    ToolError,
    ToolResult,
)
from shop_desk.tools import catalogue_tool, CatalogueQuery


class SearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., description="Search query for products")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=50)


class CategoryBrowseInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: str = Field(..., description="Category to browse")
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=50)


class SearchAgent(BaseAgent[SearchInput]):
    def __init__(self, model: str | None = None):
        super().__init__(
            name="SearchAgent",
            path=Path.FAST,
            model=model,
            use_dynamic_prompt=True,
        )

    async def run(self, input_data: SearchInput, context: ShopContext) -> ToolResult:
        result = catalogue_tool(CatalogueQuery(
            action="search",
            query=input_data.query,
            page=input_data.page,
            page_size=input_data.page_size,
        ))
        if not result.ok:
            return ToolResult.failure(result.error.code, result.error.message)

        results: list[SearchResult] = result.data
        if not results:
            return ToolResult.success(f"No products found matching '{input_data.query}'")

        lines = [f"Search results for '{input_data.query}':"]
        for i, r in enumerate(results, 1):
            stock_status = "out of stock" if r.stock == 0 else f"{r.stock} in stock"
            lines.append(
                f"{i}. SKU: {r.sku} | {r.name} | {context.currency} {r.price:,} | {stock_status} | {r.category}"
            )
        
        return ToolResult.success("\n".join(lines))


class CategoryBrowseAgent(BaseAgent[CategoryBrowseInput]):
    def __init__(self, model: str | None = None):
        super().__init__(
            name="CategoryBrowseAgent",
            path=Path.FAST,
            model=model,
            use_dynamic_prompt=True,
        )

    async def run(self, input_data: CategoryBrowseInput, context: ShopContext) -> ToolResult:
        result = catalogue_tool(CatalogueQuery(
            action="category",
            category=input_data.category,
            page=input_data.page,
            page_size=input_data.page_size,
        ))
        if not result.ok:
            return ToolResult.failure(result.error.code, result.error.message)

        results: list[SearchResult] = result.data
        if not results:
            return ToolResult.success(f"No products found in category '{input_data.category}'")

        lines = [f"Products in '{input_data.category}' category:"]
        for i, r in enumerate(results, 1):
            stock_status = "out of stock" if r.stock == 0 else f"{r.stock} in stock"
            lines.append(
                f"{i}. SKU: {r.sku} | {r.name} | {context.currency} {r.price:,} | {stock_status}"
            )
        
        return ToolResult.success("\n".join(lines))


async def handle_search(query: str, context: ShopContext, page: int = 1, page_size: int = 10, model: str | None = None) -> ToolResult:
    agent = SearchAgent(model=model)
    return await agent.run(SearchInput(query=query, page=page, page_size=page_size), context)


async def handle_category_browse(category: str, context: ShopContext, page: int = 1, page_size: int = 20, model: str | None = None) -> ToolResult:
    agent = CategoryBrowseAgent(model=model)
    return await agent.run(CategoryBrowseInput(category=category, page=page, page_size=page_size), context)