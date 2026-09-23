"""FR-1 + FR-5..FR-9 — Ops Desk agent assembly."""

from __future__ import annotations

from agents import Agent, ToolsToFinalOutputResult

from ops_desk.config import AGENT_MODEL, MAX_TURNS
from ops_desk.guardrails import build_input_guardrail
from ops_desk.profile import StudentProfile
from ops_desk.prompts import build_system_prompt
from ops_desk.specialists import (
    build_base_agent,
    build_specialists,
    build_summarise_tool,
)
from ops_desk.ticket import Ticket
from ops_desk.tools import tools_for_tier

DESK_NAME = "OpsDesk"
CLOSE_TICKET_TOOL = "close_ticket"


async def _close_ticket_is_final(ctx, tool_results) -> ToolsToFinalOutputResult:
    """FR-7 + FR-9 — close_ticket output becomes the final Ticket and ends the run."""
    for result in tool_results:
        tool_name = getattr(result.tool, "name", "")
        if tool_name != CLOSE_TICKET_TOOL:
            continue
        output = result.output
        if isinstance(output, Ticket):
            return ToolsToFinalOutputResult(is_final_output=True, final_output=output)
        if isinstance(output, dict):
            try:
                return ToolsToFinalOutputResult(
                    is_final_output=True,
                    final_output=Ticket.model_validate(output),
                )
            except Exception:  # noqa: BLE001 — fall through to non-final
                continue
    return ToolsToFinalOutputResult(is_final_output=False, final_output=None)


def build_desk_agent(profile: StudentProfile) -> Agent[StudentProfile]:
    """Desk: dynamic instructions, tier tools, handoffs, guardrail, Ticket output (FR-4..FR-9)."""
    instructions = build_system_prompt(profile)
    base = build_base_agent()
    assignments, careers = build_specialists(base)

    # Summariser is a tool on the Desk only — Desk keeps the conversation (FR-6).
    summarise = build_summarise_tool(base)

    desk_tools = tools_for_tier(profile.tier) + [summarise]

    return Agent[StudentProfile](
        name=DESK_NAME,
        model=AGENT_MODEL,  # agent-level (FR-1)
        instructions=instructions,
        tools=desk_tools,
        handoffs=[assignments, careers],  # specialist answers directly (FR-5)
        input_guardrails=[build_input_guardrail()],  # FR-8
        output_type=Ticket,  # FR-7
        # FR-7 + FR-9 — close_ticket output becomes final Ticket and ends the run
        tool_use_behavior=_close_ticket_is_final,
    )


def resolved_instructions(profile: StudentProfile) -> str:
    """Expose the prompt that will be used — printable before Runner.run (FR-4)."""
    return build_system_prompt(profile)


def offered_tool_names(profile: StudentProfile) -> list[str]:
    """Names the model would see for this tier (FR-9)."""
    desk_tools = tools_for_tier(profile.tier) + [build_summarise_tool()]
    return [t.name for t in desk_tools]


__all__ = [
    "DESK_NAME",
    "MAX_TURNS",
    "build_desk_agent",
    "offered_tool_names",
    "resolved_instructions",
]
