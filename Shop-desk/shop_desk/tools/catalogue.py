from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from shop_desk.config.settings import get_settings
from shop_desk.models.shop import (
    CatalogueEntry,
    SearchResult,
    ToolError,
    ToolResult,
)


_CATALOGUE_CACHE: dict[str, CatalogueEntry] = {}
_CATALOGUE_VERSION: str = ""
_CACHE_LOCK = threading.RLock()


class CatalogueQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["get", "search", "category", "multi_get", "version"]
    sku: Optional[str] = None
    skus: Optional[list[str]] = None
    query: Optional[str] = None
    category: Optional[str] = None
    page: int = 1
    page_size: int = 20


def _load_catalogue() -> tuple[dict[str, CatalogueEntry], str]:
    settings = get_settings()
    path = Path(settings.catalogue_path)
    if not path.exists():
        raise FileNotFoundError(f"Catalogue not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    version = data.get("version", "unknown")
    products = data.get("products", [])

    catalogue = {}
    for p in products:
        entry = CatalogueEntry(**p)
        catalogue[entry.sku] = entry

    return catalogue, version


def _ensure_loaded() -> None:
    global _CATALOGUE_CACHE, _CATALOGUE_VERSION
    with _CACHE_LOCK:
        if not _CATALOGUE_CACHE:
            _CATALOGUE_CACHE, _CATALOGUE_VERSION = _load_catalogue()


def _fuzzy_match(query: str, text: str) -> float:
    query = query.lower().strip()
    text = text.lower().strip()
    if query in text:
        return 1.0
    query_words = set(query.split())
    text_words = set(text.split())
    if not query_words:
        return 0.0
    intersection = query_words & text_words
    return len(intersection) / len(query_words)


def catalogue_tool(query: CatalogueQuery) -> ToolResult:
    _ensure_loaded()

    settings = get_settings()
    if query.action == "version":
        return ToolResult.success(_CATALOGUE_VERSION)

    if settings.catalogue_version and _CATALOGUE_VERSION != settings.catalogue_version:
        return ToolResult.failure(
            "VERSION_MISMATCH",
            f"Catalogue version {_CATALOGUE_VERSION} does not match expected {settings.catalogue_version}",
        )

    if query.action == "get":
        if not query.sku:
            return ToolResult.failure("INVALID_QUERY", "sku is required for get action")
        entry = _CATALOGUE_CACHE.get(query.sku)
        if not entry:
            return ToolResult.failure("NOT_FOUND", f"SKU {query.sku} not found")
        return ToolResult.success(entry)

    if query.action == "multi_get":
        if not query.skus:
            return ToolResult.failure("INVALID_QUERY", "skus list is required for multi_get action")
        results = []
        for sku in query.skus:
            entry = _CATALOGUE_CACHE.get(sku)
            if entry:
                results.append(entry)
        return ToolResult.success(results)

    if query.action == "search":
        if not query.query:
            return ToolResult.failure("INVALID_QUERY", "query is required for search action")
        scored = []
        for entry in _CATALOGUE_CACHE.values():
            score = _fuzzy_match(query.query, entry.name)
            if score > 0:
                scored.append((score, entry))
        scored.sort(key=lambda x: x[0], reverse=True)
        page_size = query.page_size or settings.default_page_size
        start = (query.page - 1) * page_size
        end = start + page_size
        results = [
            SearchResult(
                sku=e.sku,
                name=e.name,
                price=e.price,
                stock=e.stock,
                category=e.category,
                relevance_score=s,
            )
            for s, e in scored[start:end]
        ]
        return ToolResult.success(results)

    if query.action == "category":
        if not query.category:
            return ToolResult.failure("INVALID_QUERY", "category is required for category action")
        filtered = [
            e for e in _CATALOGUE_CACHE.values() if e.category.lower() == query.category.lower()
        ]
        page_size = query.page_size or settings.default_page_size
        start = (query.page - 1) * page_size
        end = start + page_size
        results = [
            SearchResult(
                sku=e.sku,
                name=e.name,
                price=e.price,
                stock=e.stock,
                category=e.category,
                relevance_score=1.0,
            )
            for e in filtered[start:end]
        ]
        return ToolResult.success(results)

    return ToolResult.failure("INVALID_QUERY", f"Unknown action: {query.action}")


def reload_catalogue() -> tuple[dict[str, CatalogueEntry], str]:
    global _CATALOGUE_CACHE, _CATALOGUE_VERSION
    with _CACHE_LOCK:
        _CATALOGUE_CACHE, _CATALOGUE_VERSION = _load_catalogue()
    return _CATALOGUE_CACHE, _CATALOGUE_VERSION


def get_catalogue_version() -> str:
    _ensure_loaded()
    return _CATALOGUE_VERSION