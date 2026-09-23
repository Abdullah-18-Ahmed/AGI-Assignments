"""FR-10 / NFR-3 — ordered audit timeline via run hooks + one watched specialist."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from agents import Agent, AgentHooks, RunContextWrapper, RunHooks

from ops_desk.specialists import ASSIGNMENTS_NAME

# Durable sink (NFR-3) — not print-only.
AUDIT_DIR = Path(__file__).resolve().parent.parent / "audit"
TIMELINE_PATH = AUDIT_DIR / "timeline.jsonl"


@dataclass
class TimelineEvent:
    seq: int
    ts: float
    kind: str
    agent: str
    detail: dict[str, Any] = field(default_factory=dict)


class TimelineRecorder:
    """Append-only ordered timeline; flushed to disk on every event (durable)."""

    def __init__(self, path: Path = TIMELINE_PATH) -> None:
        self.path = path
        self.events: list[TimelineEvent] = []
        self._seq = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, kind: str, agent: str, **detail: Any) -> TimelineEvent:
        self._seq += 1
        event = TimelineEvent(
            seq=self._seq,
            ts=time.time(),
            kind=kind,
            agent=agent,
            detail=detail,
        )
        self.events.append(event)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(asdict(event), ensure_ascii=False) + "\n")
        return event

    def clear_memory(self) -> None:
        """Start a new conversation file segment without deleting history."""
        self.events.clear()
        self._seq = 0

    def agent_order(self) -> list[str]:
        """Distinct agents in timeline order (for FR-10 done-when)."""
        ordered: list[str] = []
        for event in self.events:
            if event.agent and event.agent not in ordered:
                ordered.append(event.agent)
        return ordered


# Process-wide recorder (one conversation run appends in order).
RECORDER = TimelineRecorder()


class AuditRunHooks(RunHooks):
    """Run-level hooks: every agent in the conversation, including handoffs (FR-10)."""

    def __init__(self, recorder: TimelineRecorder | None = None) -> None:
        self.recorder = recorder or RECORDER

    async def on_agent_start(self, context: Any, agent: Agent) -> None:
        self.recorder.record("agent_start", agent.name)

    async def on_agent_end(self, context: Any, agent: Agent, output: Any) -> None:
        out_type = type(output).__name__
        self.recorder.record("agent_end", agent.name, output_type=out_type)

    async def on_handoff(
        self,
        context: RunContextWrapper,
        from_agent: Agent,
        to_agent: Agent,
    ) -> None:
        self.recorder.record(
            "handoff",
            from_agent.name,
            to=to_agent.name,
        )
        self.recorder.record("handoff_arrive", to_agent.name, **{"from": from_agent.name})

    async def on_llm_start(
        self,
        context: RunContextWrapper,
        agent: Agent,
        system_prompt: str | None,
        input_items: list,
    ) -> None:
        self.recorder.record(
            "llm_start",
            agent.name,
            system_prompt_chars=len(system_prompt or ""),
            input_items=len(input_items or []),
        )

    async def on_llm_end(self, context: RunContextWrapper, agent: Agent, response: Any) -> None:
        self.recorder.record("llm_end", agent.name)

    async def on_tool_start(
        self,
        context: RunContextWrapper,
        agent: Agent,
        tool: Any,
    ) -> None:
        self.recorder.record("tool_start", agent.name, tool=getattr(tool, "name", "?"))

    async def on_tool_end(
        self,
        context: RunContextWrapper,
        agent: Agent,
        tool: Any,
        result: object,
    ) -> None:
        self.recorder.record(
            "tool_end",
            agent.name,
            tool=getattr(tool, "name", "?"),
            result_type=type(result).__name__,
        )


class WatchedSpecialistHooks(AgentHooks):
    """Agent-level hooks on exactly one specialist (Assignments) — FR-10.

    These fire only for events on this agent instance. After a handoff transfers
    the conversation to another agent, they go quiet; run-level hooks keep recording.
    """

    WATCHED_AGENT = ASSIGNMENTS_NAME

    def __init__(self, recorder: TimelineRecorder | None = None) -> None:
        self.recorder = recorder or RECORDER

    async def on_start(self, context: Any, agent: Agent) -> None:
        self.recorder.record(
            "agent_hooks_start",
            agent.name,
            watched=self.WATCHED_AGENT,
            scope="agent_level",
        )

    async def on_end(self, context: Any, agent: Agent, output: Any) -> None:
        self.recorder.record(
            "agent_hooks_end",
            agent.name,
            scope="agent_level",
            output_type=type(output).__name__,
        )

    async def on_llm_start(
        self,
        context: RunContextWrapper,
        agent: Agent,
        system_prompt: str | None,
        input_items: list,
    ) -> None:
        self.recorder.record(
            "agent_hooks_llm_start",
            agent.name,
            scope="agent_level",
        )

    async def on_llm_end(self, context: RunContextWrapper, agent: Agent, response: Any) -> None:
        self.recorder.record(
            "agent_hooks_llm_end",
            agent.name,
            scope="agent_level",
        )

    async def on_tool_start(self, context: RunContextWrapper, agent: Agent, tool: Any) -> None:
        self.recorder.record(
            "agent_hooks_tool_start",
            agent.name,
            scope="agent_level",
            tool=getattr(tool, "name", "?"),
        )

    async def on_tool_end(
        self,
        context: RunContextWrapper,
        agent: Agent,
        tool: Any,
        result: object,
    ) -> None:
        self.recorder.record(
            "agent_hooks_tool_end",
            agent.name,
            scope="agent_level",
            tool=getattr(tool, "name", "?"),
        )

    async def on_handoff(self, context: RunContextWrapper, agent: Agent, source: Agent) -> None:
        self.recorder.record(
            "agent_hooks_handoff",
            agent.name,
            scope="agent_level",
            source=source.name if source else "?",
        )


def watched_specialist_hooks() -> WatchedSpecialistHooks:
    return WatchedSpecialistHooks()
