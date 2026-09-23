"""FR-8 — input guardrail: refuse non-course questions before the Desk model runs."""

from __future__ import annotations

from typing import Any

from agents import Agent, GuardrailFunctionOutput, InputGuardrail, RunContextWrapper

from ops_desk.profile import StudentProfile

# Heuristic only — no model call, so refusal costs nothing at gpt-4o-mini (FR-8).
_OUT_OF_SCOPE_MARKERS: tuple[str, ...] = (
    "weather",
    "football",
    "cricket score",
    "stock price",
    "bitcoin",
    "cryptocurrency",
    "recipe",
    "cook ",
    "movie review",
    "tell me a joke",
    "sing a song",
    "horoscope",
    "lottery",
)

_IN_SCOPE_MARKERS: tuple[str, ...] = (
    "assignment",
    "course",
    "schedule",
    "syllabus",
    "policy",
    "due ",
    "deadline",
    "career",
    "resume",
    "cv ",
    "interview",
    "job ",
    "scholarship",
    "exam",
    "class",
    "lecture",
    "batch",
    "saylani",
    "bootcamp",
    "roll",
    "ticket",
    "enroll",
    "certificate",
)


def extract_user_text(input_data: str | list[Any]) -> str:
    """Best-effort pull of student message text from Runner input."""
    if isinstance(input_data, str):
        return input_data
    parts: list[str] = []
    if not isinstance(input_data, list):
        return ""
    for item in input_data:
        if isinstance(item, str):
            parts.append(item)
            continue
        if not isinstance(item, dict):
            continue
        if item.get("role") not in (None, "user"):
            continue
        content = item.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict):
                    text = part.get("text") or part.get("input_text")
                    if isinstance(text, str):
                        parts.append(text)
    return "\n".join(parts).strip()


def is_off_topic(text: str) -> bool:
    """True when the message is clearly not about the bootcamp."""
    lowered = text.lower()
    if not lowered.strip():
        return False
    if any(marker in lowered for marker in _IN_SCOPE_MARKERS):
        return False
    return any(marker in lowered for marker in _OUT_OF_SCOPE_MARKERS)


async def course_scope_guardrail(
    ctx: RunContextWrapper[StudentProfile],
    agent: Agent[StudentProfile],
    input_data: str | list[Any],
) -> GuardrailFunctionOutput:
    """Tripwire before Desk model runs. Free (no LLM) — NFR cost / FR-8."""
    text = extract_user_text(input_data)
    off = is_off_topic(text)
    return GuardrailFunctionOutput(
        output_info={
            "off_topic": off,
            "excerpt": text[:200],
            "method": "keyword_heuristic_no_llm",
        },
        tripwire_triggered=off,
    )


def build_input_guardrail() -> InputGuardrail[StudentProfile]:
    return InputGuardrail[StudentProfile](
        guardrail_function=course_scope_guardrail,
        name="CourseScopeGuardrail",
        run_in_parallel=True,
    )


POLITE_REFUSAL = (
    "hey — i'm only good for this bootcamp tbh 😅\n\n"
    "assignments, class stuff, policies, careers in the program — "
    "those i'm all over. anything outside that, i'll have to sit out.\n\n"
    "got a question about your course? i'm right here!"
)
