"""FR-7 — structured Ticket final output (Pydantic, not prose)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Ticket(BaseModel):
    """Typed close-out for a resolved Desk conversation."""

    category: Literal["assignment", "career", "admin"]
    summary: str = Field(
        description=(
            "Your chat reply TO the student — second person (you/your), friendly, "
            "include the real facts you looked up (ids, titles, dates, policies). "
            "Never write about them in third person."
        )
    )
    next_step: str = Field(
        description="What you tell the student to do next, still second person and concrete"
    )
    resolved: bool = Field(description="True if the query was fully answered")
    escalate: bool = Field(description="True if a human must follow up")
