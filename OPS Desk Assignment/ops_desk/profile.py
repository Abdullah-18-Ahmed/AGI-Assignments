"""StudentProfile local context (FR-3)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StudentProfile:
    """Passed to every run as local context — not stuffed into prompt text as a wrapper."""

    name: str
    roll_no: str
    course_id: str
    tier: str = "regular"  # "regular" or "scholarship"
    open_tickets: int = 0
