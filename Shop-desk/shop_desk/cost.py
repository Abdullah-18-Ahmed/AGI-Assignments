from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Optional

from shop_desk.config.settings import get_settings
from shop_desk.models.shop import (
    Path,
    SessionSummary,
    TokenUsage,
    TraceEntry,
    TurnCost,
    RunCostSummary,
    LifecycleEvent,
    EscalationHandoff,
    EscalationReason,
    HistoryEntry,
    ShopContext,
)
from shop_desk.tools import trace_tool, TraceQuery


# OpenAI pricing (USD per 1M tokens) - as of 2024
MODEL_PRICING = {
    "openai/gpt-4o-mini": {"prompt": 0.15, "completion": 0.60},
    "openai/gpt-4o": {"prompt": 5.00, "completion": 15.00},
    "gpt-4o-mini": {"prompt": 0.15, "completion": 0.60},
    "gpt-4o": {"prompt": 5.00, "completion": 15.00},
}


def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> tuple[float, float, float]:
    """Calculate cost in USD for a model call."""
    pricing = MODEL_PRICING.get(model, {"prompt": 0.0, "completion": 0.0})
    prompt_cost = (prompt_tokens / 1_000_000) * pricing["prompt"]
    completion_cost = (completion_tokens / 1_000_000) * pricing["completion"]
    return prompt_cost, completion_cost, prompt_cost + completion_cost


class LifecycleHook(ABC):
    """Abstract base for lifecycle hooks."""

    @abstractmethod
    def on_run_start(self, session_id: str) -> None:
        pass

    @abstractmethod
    def on_turn_start(self, session_id: str, turn_number: int, agent: str, model: str, path: Path) -> None:
        pass

    @abstractmethod
    def on_turn_end(
        self,
        session_id: str,
        turn_number: int,
        agent: str,
        model: str,
        path: Path,
        tokens: TokenUsage,
    ) -> None:
        pass

    @abstractmethod
    def on_run_end(self, session_id: str, summary: RunCostSummary) -> None:
        pass

    @abstractmethod
    def on_handoff(self, handoff: EscalationHandoff) -> None:
        pass


@dataclass
class CostTracker:
    """Tracks costs across a run/session."""
    
    session_id: str
    turns: list[TurnCost] = field(default_factory=list)
    model_breakdown: dict[str, dict[str, float]] = field(default_factory=lambda: {})
    
    def record_turn(
        self,
        turn_number: int,
        agent: str,
        model: str,
        path: Path,
        tokens: TokenUsage,
    ) -> TurnCost:
        prompt_cost, completion_cost, total_cost = calculate_cost(
            model, tokens.prompt_tokens, tokens.completion_tokens
        )
        
        turn_cost = TurnCost(
            turn_number=turn_number,
            agent=agent,
            model=model,
            path=path,
            prompt_tokens=tokens.prompt_tokens,
            completion_tokens=tokens.completion_tokens,
            total_tokens=tokens.total_tokens,
            prompt_cost_usd=prompt_cost,
            completion_cost_usd=completion_cost,
            total_cost_usd=total_cost,
            timestamp=time.time(),
        )
        self.turns.append(turn_cost)
        
        # Update model breakdown
        if model not in self.model_breakdown:
            self.model_breakdown[model] = {"prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0}
        self.model_breakdown[model]["prompt_tokens"] += tokens.prompt_tokens
        self.model_breakdown[model]["completion_tokens"] += tokens.completion_tokens
        self.model_breakdown[model]["cost"] += total_cost
        
        return turn_cost
    
    def get_summary(self) -> RunCostSummary:
        total_prompt = sum(t.prompt_tokens for t in self.turns)
        total_completion = sum(t.completion_tokens for t in self.turns)
        total_cost = sum(t.total_cost_usd for t in self.turns)
        
        fast_path_turns = [t for t in self.turns if t.path == Path.FAST]
        reasoning_turns = [t for t in self.turns if t.path == Path.REASONING]
        
        return RunCostSummary(
            session_id=self.session_id,
            total_turns=len(self.turns),
            total_prompt_tokens=total_prompt,
            total_completion_tokens=total_completion,
            total_tokens=total_prompt + total_completion,
            total_cost_usd=total_cost,
            fast_path_turns=len(fast_path_turns),
            fast_path_cost_usd=sum(t.total_cost_usd for t in fast_path_turns),
            reasoning_path_turns=len(reasoning_turns),
            reasoning_path_cost_usd=sum(t.total_cost_usd for t in reasoning_turns),
            model_breakdown=self.model_breakdown,
            turns=self.turns,
        )


class LifecycleManager:
    """Manages lifecycle hooks and cost tracking for a run."""
    
    def __init__(self, hooks: Optional[list[LifecycleHook]] = None):
        self.hooks = hooks or []
        self.trackers: dict[str, CostTracker] = {}
        self._turn_counts: dict[str, int] = {}
    
    def _get_tracker(self, session_id: str) -> CostTracker:
        if session_id not in self.trackers:
            self.trackers[session_id] = CostTracker(session_id=session_id)
            self._turn_counts[session_id] = 0
        return self.trackers[session_id]
    
    def _next_turn(self, session_id: str) -> int:
        self._turn_counts[session_id] += 1
        return self._turn_counts[session_id]
    
    def run_start(self, session_id: str) -> None:
        tracker = self._get_tracker(session_id)
        event = LifecycleEvent(
            event_type="run_start",
            session_id=session_id,
            turn_number=0,
            agent="system",
            model="",
            path=Path.FAST,
            timestamp=time.time(),
        )
        for hook in self.hooks:
            hook.on_run_start(session_id)
    
    def turn_start(
        self,
        session_id: str,
        agent: str,
        model: str,
        path: Path,
    ) -> int:
        turn_number = self._next_turn(session_id)
        event = LifecycleEvent(
            event_type="turn_start",
            session_id=session_id,
            turn_number=turn_number,
            agent=agent,
            model=model,
            path=path,
            timestamp=time.time(),
        )
        for hook in self.hooks:
            hook.on_turn_start(session_id, turn_number, agent, model, path)
        return turn_number
    
    def turn_end(
        self,
        session_id: str,
        turn_number: int,
        agent: str,
        model: str,
        path: Path,
        tokens: TokenUsage,
    ) -> TurnCost:
        tracker = self._get_tracker(session_id)
        turn_cost = tracker.record_turn(turn_number, agent, model, path, tokens)
        
        for hook in self.hooks:
            hook.on_turn_end(session_id, turn_number, agent, model, path, tokens)
        
        return turn_cost
    
    def run_end(self, session_id: str) -> RunCostSummary:
        tracker = self._get_tracker(session_id)
        summary = tracker.get_summary()
        
        for hook in self.hooks:
            hook.on_run_end(session_id, summary)
        
        return summary
    
    def handoff(
        self,
        session_id: str,
        reason: EscalationReason,
        summary: str,
        history: list[HistoryEntry],
        context: ShopContext,
    ) -> EscalationHandoff:
        """Create escalation handoff with filtered history and cost summary."""
        tracker = self._get_tracker(session_id)
        cost_summary = tracker.get_summary()
        
        # Filter history: remove tool call outputs, retain user/assistant messages with intent
        filtered_history = self._filter_history_for_handoff(history)
        
        handoff = EscalationHandoff(
            session_id=session_id,
            reason=reason,
            summary=summary,
            filtered_history=filtered_history,
            original_turn_count=len(history),
            filtered_turn_count=len(filtered_history),
            cost_summary=cost_summary,
            timestamp=time.time(),
        )
        
        for hook in self.hooks:
            hook.on_handoff(handoff)
        
        return handoff
    
    def _filter_history_for_handoff(self, history: list[HistoryEntry]) -> list[HistoryEntry]:
        """Filter conversation history for human escalation.
        
        Removes:
        - Tool call/result noise (internal system messages)
        - Raw token usage data
        - Verbose catalogue dumps
        
        Retains:
        - User messages (intent)
        - Assistant responses (key information given)
        - Error messages (context for human)
        """
        filtered = []
        
        for entry in history:
            # Keep user messages always
            if entry.role == "user":
                filtered.append(entry)
                continue
            
            # Keep assistant messages but trim tool noise
            if entry.role == "assistant":
                # Skip if it looks like a raw tool result
                content = entry.content.lower()
                if any(noise in content for noise in [
                    "toolresult", "catalogueentry", "searchresult", 
                    "tokenusage", "traceentry", "session_summary"
                ]):
                    continue
                # Skip if it's just a raw JSON dump
                if content.strip().startswith("{") and "sku" in content and "price" in content:
                    continue
                filtered.append(entry)
                continue
            
            # Keep system messages that are errors/warnings
            if entry.role == "system":
                content = entry.content.lower()
                if any(keyword in content for keyword in ["error", "warning", "limit", "failed"]):
                    filtered.append(entry)
        
        return filtered


# Default logging hook
class LoggingLifecycleHook(LifecycleHook):
    """Logs lifecycle events to console/file."""
    
    def on_run_start(self, session_id: str) -> None:
        print(f"[LIFECYCLE] Run started: {session_id}")
    
    def on_turn_start(self, session_id: str, turn_number: int, agent: str, model: str, path: Path) -> None:
        print(f"[LIFECYCLE] Turn {turn_number} start: {agent} ({model}, {path.value})")
    
    def on_turn_end(
        self,
        session_id: str,
        turn_number: int,
        agent: str,
        model: str,
        path: Path,
        tokens: TokenUsage,
    ) -> None:
        prompt_cost, completion_cost, total_cost = calculate_cost(model, tokens.prompt_tokens, tokens.completion_tokens)
        print(f"[LIFECYCLE] Turn {turn_number} end: {agent} - {tokens.total_tokens} tokens (${total_cost:.6f})")
    
    def on_run_end(self, session_id: str, summary: RunCostSummary) -> None:
        print(f"[LIFECYCLE] Run ended: {session_id}")
        print(f"  Total turns: {summary.total_turns}")
        print(f"  Total tokens: {summary.total_tokens} (${summary.total_cost_usd:.6f})")
        print(f"  Fast path: {summary.fast_path_turns} turns (${summary.fast_path_cost_usd:.6f})")
        print(f"  Reasoning: {summary.reasoning_path_turns} turns (${summary.reasoning_path_cost_usd:.6f})")
        for model, data in summary.model_breakdown.items():
            print(f"  {model}: {data['prompt_tokens']} prompt + {data['completion_tokens']} completion = ${data['cost']:.6f}")
    
    def on_handoff(self, handoff: EscalationHandoff) -> None:
        print(f"[LIFECYCLE] HANDOFF: {handoff.session_id} - {handoff.reason.value}")
        print(f"  History: {handoff.original_turn_count} -> {handoff.filtered_turn_count} entries")
        print(f"  Cost so far: ${handoff.cost_summary.total_cost_usd:.6f}")


# Global lifecycle manager
_lifecycle_manager = LifecycleManager(hooks=[LoggingLifecycleHook()])


def get_lifecycle_manager() -> LifecycleManager:
    return _lifecycle_manager


def add_lifecycle_hook(hook: LifecycleHook) -> None:
    _lifecycle_manager.hooks.append(hook)


def remove_lifecycle_hook(hook: LifecycleHook) -> None:
    if hook in _lifecycle_manager.hooks:
        _lifecycle_manager.hooks.remove(hook)