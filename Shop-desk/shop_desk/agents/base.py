from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Generic, Optional, TypeVar

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
)
from shop_desk.tools import trace_tool, TraceQuery
from shop_desk.prompts.dynamic import generate_fast_path_prompt, generate_reasoning_prompt


T = TypeVar("T", bound=BaseModel)


DEFAULT_FAST_MODEL = "openai/gpt-4o-mini"
DEFAULT_REASONING_MODEL = "openai/gpt-4o"


def get_default_model(path: Path) -> str:
    settings = get_settings()
    if path == Path.FAST:
        return settings.fast_model or DEFAULT_FAST_MODEL
    return settings.reasoning_model or DEFAULT_REASONING_MODEL


class BaseAgent(ABC, Generic[T]):
    def __init__(
        self,
        name: str,
        path: Path,
        model: Optional[str] = None,
        use_dynamic_prompt: bool = True,
    ):
        self.name = name
        self.path = path
        self.model = model or get_default_model(path)
        self._client: Optional[AsyncOpenAI] = None
        self.use_dynamic_prompt = use_dynamic_prompt

    @property
    def client(self) -> AsyncOpenAI:
        if self._client is None:
            settings = get_settings()
            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._client

    def _get_system_prompt(self, context: ShopContext) -> str:
        if self.use_dynamic_prompt:
            if self.path == Path.FAST:
                return generate_fast_path_prompt(context)
            else:
                return generate_reasoning_prompt(context)
        return ""

    @abstractmethod
    async def run(self, input_data: T, context: ShopContext) -> ToolResult:
        pass

    async def _call_llm(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
    ) -> tuple[str, TokenUsage]:
        start = time.time()
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        elapsed = time.time() - start

        content = response.choices[0].message.content or ""
        usage = response.usage

        token_usage = TokenUsage(
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
            model=self.model,
        )

        trace_entry = TraceEntry(
            model=self.model,
            path=self.path,
            prompt_tokens=token_usage.prompt_tokens,
            completion_tokens=token_usage.completion_tokens,
            total_tokens=token_usage.total_tokens,
            turn_count=1,
            agent=self.name,
            timestamp=time.time(),
        )

        trace_tool(TraceQuery(action="log", entry=trace_entry))

        return content, token_usage

    def _build_messages(self, user_content: str, context: ShopContext) -> list[dict[str, str]]:
        system_prompt = self._get_system_prompt(context)
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

    def _validate_response(self, content: str, context: ShopContext) -> str:
        return content