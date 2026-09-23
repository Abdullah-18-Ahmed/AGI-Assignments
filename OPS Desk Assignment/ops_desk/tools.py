"""FR-2 course tools + FR-3 profile context tool. Tools never raise to the caller (NFR-4)."""

from __future__ import annotations

from typing import Literal

from agents import RunContextWrapper, function_tool

from ops_desk.course_store import (
    CourseDataError,
    find_assignment,
    find_course,
    load_courses,
)
from ops_desk.profile import StudentProfile
from ops_desk.ticket import Ticket

# RunContextWrapper is injected by the SDK and is not part of the tool JSON schema (FR-3).
ReadContext = RunContextWrapper[StudentProfile]


def _unavailable(what: str, detail: str) -> str:
    return f"{what} is unavailable right now: {detail}. Do not invent an answer; tell the student to try again later or contact course admin."


@function_tool
def list_courses() -> str:
    """List all course ids and titles available on the Ops Desk."""
    try:
        courses = load_courses()["courses"]
    except CourseDataError as exc:
        return _unavailable("Course catalog", str(exc))
    except Exception as exc:  # noqa: BLE001 — NFR-4: never raise to runner
        return _unavailable("Course catalog", str(exc))
    if not courses:
        return "No courses are published in the catalog yet. Say the catalog is empty."
    lines = [f"{c.get('id')}: {c.get('title')}" for c in courses]
    return "Available courses:\n" + "\n".join(lines)


@function_tool
def get_course(course_id: str) -> str:
    """Fetch one course's schedule, policies, and assignment list by course id."""
    try:
        course = find_course(course_id)
    except CourseDataError as exc:
        return _unavailable("Course detail", str(exc))
    except Exception as exc:  # noqa: BLE001
        return _unavailable("Course detail", str(exc))
    if course is None:
        known = []
        try:
            known = [str(c.get("id")) for c in load_courses()["courses"]]
        except Exception:  # noqa: BLE001
            known = []
        return (
            f"No course with id '{course_id}' exists in courses.json. "
            f"Known ids: {', '.join(known) or 'none'}. Do not invent a course id."
        )
    policies = course.get("policies") or {}
    policy_txt = "\n".join(f"  - {k}: {v}" for k, v in policies.items()) or "  - none listed"
    assignments = course.get("assignments") or []
    assign_txt = (
        "\n".join(
            f"  - {a.get('id')}: {a.get('title')} (due {a.get('due')})" for a in assignments
        )
        or "  - none listed"
    )
    return (
        f"Course: {course.get('title')} ({course.get('id')})\n"
        f"Schedule: {course.get('schedule')}\n"
        f"Policies:\n{policy_txt}\n"
        f"Assignments:\n{assign_txt}"
    )


@function_tool
def get_assignment(assignment_id: str) -> str:
    """Look up a single assignment by its id (unique across courses)."""
    try:
        hit = find_assignment(assignment_id)
    except CourseDataError as exc:
        return _unavailable("Assignment lookup", str(exc))
    except Exception as exc:  # noqa: BLE001
        return _unavailable("Assignment lookup", str(exc))
    if hit is None:
        return (
            f"No assignment with id '{assignment_id}' exists in courses.json. "
            "Do not invent an assignment id; offer list_courses or get_course instead."
        )
    course, assignment = hit
    return (
        f"Assignment {assignment.get('id')}: {assignment.get('title')}\n"
        f"Due: {assignment.get('due')}\n"
        f"Course: {course.get('title')} ({course.get('id')})\n"
        f"Schedule: {course.get('schedule')}"
    )


@function_tool
def get_student_context(ctx: ReadContext) -> str:
    """Read the current student's enrollment context (course_id, tier, open_tickets).

    Student fields come from run local context only — no student wrapper parameters.
    """
    profile = ctx.context
    if not isinstance(profile, StudentProfile):
        return "Student profile is not attached to this run. Ask the operator to set context."
    return (
        f"course_id={profile.course_id}; "
        f"tier={profile.tier}; "
        f"open_tickets={profile.open_tickets}"
    )


def _scholarship_enabled(ctx: ReadContext, agent: object) -> bool:
    """FR-9 — hide scholarship tool unless tier is scholarship (absent, not refused)."""
    profile = ctx.context
    if not isinstance(profile, StudentProfile):
        return False
    return profile.tier == "scholarship"


@function_tool(is_enabled=_scholarship_enabled)
def get_scholarship_benefits() -> str:
    """Scholarship-only benefits: stipend schedule, required check-ins, form links."""
    try:
        return (
            "Scholarship track benefits: monthly stipend after attendance check; "
            "priority career-coaching slots; required mentor check-in every two weeks. "
            "Confirm details with the scholarship desk for your batch."
        )
    except Exception as exc:  # noqa: BLE001 — NFR-4
        return _unavailable("Scholarship benefits", str(exc))


@function_tool
def close_ticket(
    category: Literal["assignment", "career", "admin"],
    summary: str,
    next_step: str,
    resolved: bool,
    escalate: bool,
) -> dict:
    """Close this conversation now and emit the final Ticket. Ends the run immediately (FR-9).

    summary must be your second-person chat reply with the real facts (ids, titles, dates).
    """
    try:
        ticket = Ticket(
            category=category,
            summary=summary,
            next_step=next_step,
            resolved=resolved,
            escalate=escalate,
        )
        return ticket.model_dump()
    except Exception as exc:  # noqa: BLE001 — NFR-4
        return {
            "category": "admin",
            "summary": f"close_ticket failed validation: {exc}",
            "next_step": "Desk retried close with corrected fields.",
            "resolved": False,
            "escalate": True,
        }


def scholarship_only(ctx: ReadContext, agent: object) -> bool:
    return _scholarship_enabled(ctx, agent)


def tools_for_tier(tier: str) -> list:
    """FR-9 — tool list differs by tier: scholarship tool absent for regular."""
    tools: list = [
        list_courses,
        get_course,
        get_assignment,
        get_student_context,
        close_ticket,
    ]
    if tier == "scholarship":
        tools.append(get_scholarship_benefits)
    return tools


def course_tool_docs() -> list[str]:
    """Return tool names for auditability."""
    return [
        "list_courses",
        "get_course",
        "get_assignment",
        "get_student_context",
        "get_scholarship_benefits",
        "close_ticket",
    ]
