"""FR-5 / FR-6 — base agent, cloned specialists, Summariser-as-tool."""

from __future__ import annotations

from pydantic import BaseModel, Field

from agents import Agent

from ops_desk.config import AGENT_MODEL
from ops_desk.profile import StudentProfile
from ops_desk.ticket import Ticket
from ops_desk.tools import get_assignment, get_course, get_student_context, list_courses

ASSIGNMENTS_NAME = "AssignmentsSpecialist"
CAREERS_NAME = "CareersSpecialist"
SUMMARISER_NAME = "Summariser"
BASE_NAME = "OpsDeskBase"

ASSIGNMENTS_INSTRUCTIONS = (
    "You're the assignments person for Saylani. Keep it cold and factual — "
    "dates, ids, schedules, late rules only. No small talk, no career pep talks. "
    "Only answer from the course tools; never invent ids. "
    "You're talking straight to the student after a handoff from the Desk — "
    "second person (you/your), never third-person notes about them. "
    "When you're done, final output must be a valid Ticket "
    "(category assignment|career|admin, summary, next_step, resolved, escalate) "
    "where summary is your factual chat reply with the real ids, titles, and dates."
)

CAREERS_INSTRUCTIONS = (
    "You're the careers buddy for Saylani. Sound like a hype friend: "
    "internships, CVs, interview prep, next steps for this program. "
    "Stay on bootcamp career topics only. "
    "Only use facts you actually know or course tools — never invent company policies. "
    "You're talking straight to the student after a handoff from the Desk — "
    "second person (you/your), never third-person notes about them. "
    "When you're done, final output must be a valid Ticket "
    "(category assignment|career|admin, summary, next_step, resolved, escalate) "
    "where summary is your friendly chat reply with concrete next steps."
)

SUMMARISER_INSTRUCTIONS = (
    "Condense the provided text to EXACTLY three short lines. "
    "Keep the facts, ids, and deadlines. No preamble, no headers, no fourth line."
)

BASE_INSTRUCTIONS = (
    "You're the Saylani Student Ops Desk base agent — "
    "prefer specialized instructions from the active agent profile."
)


class SummariseInput(BaseModel):
    """Structured input for the Summariser agent-as-tool (FR-6)."""

    text: str = Field(description="Long policy or answer text to condense to three lines")


def core_course_tools() -> list:
    return [list_courses, get_course, get_assignment, get_student_context]


def build_base_agent() -> Agent[StudentProfile]:
    """Single base agent — model set here once (FR-5 / NFR-2)."""
    return Agent[StudentProfile](
        name=BASE_NAME,
        model=AGENT_MODEL,  # only place model is declared for the family
        instructions=BASE_INSTRUCTIONS,
        tools=core_course_tools(),
        output_type=Ticket,
    )


def build_specialists(
    base: Agent[StudentProfile] | None = None,
) -> tuple[Agent[StudentProfile], Agent[StudentProfile]]:
    """Clone Assignments + Careers from base without restating model (FR-5).

    Agent-level hooks attach to Assignments only (FR-10 — exactly one specialist).
    """
    from ops_desk.audit import watched_specialist_hooks

    root = base or build_base_agent()
    assignments = root.clone(
        name=ASSIGNMENTS_NAME,
        instructions=ASSIGNMENTS_INSTRUCTIONS,
        tools=core_course_tools(),  # fresh list — no shared mutable handoff of tools only
        # model intentionally omitted — inherits root.model
        output_type=Ticket,
        hooks=watched_specialist_hooks(),  # FR-10: only this specialist is watched
    )
    careers = root.clone(
        name=CAREERS_NAME,
        instructions=CAREERS_INSTRUCTIONS,
        tools=core_course_tools(),
        # model intentionally omitted — inherits root.model
        output_type=Ticket,
        hooks=None,  # FR-10: exactly one specialist has agent-level hooks
    )
    return assignments, careers


def build_summariser(base: Agent[StudentProfile] | None = None) -> Agent[StudentProfile]:
    root = base or build_base_agent()
    return root.clone(
        name=SUMMARISER_NAME,
        instructions=SUMMARISER_INSTRUCTIONS,
        tools=[],
        # model intentionally omitted
        output_type=None,  # returns text to Desk; Desk keeps the conversation (FR-6)
    )


def build_summarise_tool(base: Agent[StudentProfile] | None = None):
    """Expose Summariser as a tool the Desk calls (not a handoff) — FR-6."""
    summariser = build_summariser(base)
    return summariser.as_tool(
        tool_name="summarise_policy",
        tool_description=(
            "Squash a long policy or course answer down to exactly three lines. "
            "The Desk keeps the chat and delivers the result in its own voice."
        ),
        parameters=SummariseInput,
    )
