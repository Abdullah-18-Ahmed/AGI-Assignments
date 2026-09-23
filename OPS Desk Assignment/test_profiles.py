"""Fixture profiles for FR-4 prompt variants and FR-9 tier gating (no app logic)."""

from __future__ import annotations

from ops_desk.profile import StudentProfile

REGULAR_CALM = StudentProfile(
    name="Abdullah Ahmed",
    roll_no="SL-2026-0142",
    course_id="agentic-ai-w4",
    tier="regular",
    open_tickets=0,
)

REGULAR_TERSE = StudentProfile(
    name="Bilal Ahmed",
    roll_no="SL-2026-0177",
    course_id="data-eng-we2",
    tier="regular",
    open_tickets=3,
)

SCHOLARSHIP = StudentProfile(
    name="Hina Raza",
    roll_no="SL-2026-0203",
    course_id="genai-evening-b1",
    tier="scholarship",
    open_tickets=1,
)

PROFILES = {
    "regular": REGULAR_CALM,
    "terse": REGULAR_TERSE,
    "scholarship": SCHOLARSHIP,
}
