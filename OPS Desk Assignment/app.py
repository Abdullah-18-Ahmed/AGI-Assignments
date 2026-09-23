"""FR-12 — Chainlit UI: identify student on startup; agent+profile once; await run; per-session memory."""

from __future__ import annotations

import re
import uuid

import chainlit as cl
from agents import InputGuardrailTripwireTriggered, MaxTurnsExceeded, Runner

from ops_desk.agent import build_desk_agent
from ops_desk.audit import AuditRunHooks, RECORDER
from ops_desk.bootstrap import bootstrap
from ops_desk.config import MAX_TURNS, require_openai_api_key
from ops_desk.guardrails import POLITE_REFUSAL
from ops_desk.profile import StudentProfile
from ops_desk.ticket import Ticket
from ops_desk.tracing_setup import conversation_run_config
from test_profiles import PROFILES

_ROLL_RE = re.compile(r"\bSL[-\s]?\d{4}[-\s]?\d{3,4}\b", re.I)
_ROLL_CANON_RE = re.compile(r"SL-(\d{4})-(\d{3,4})", re.I)

_AWAITING_IDENTITY = "awaiting_identity"
_READY = "ready"

WELCOME_PROMPT = (
    "hello, welcome to your **study buddy** 👋\n\n"
    "i can pull up your courses, assignments, deadlines, policies, "
    "and career tips — but first i need to know who you are.\n\n"
    "drop your **full name** and **roll number**, something like:\n\n"
    "`Abdullah Ahmed · SL-2026-0142`\n\n"
    "paste both however you like — i'll match you to your courses."
)


def _canon_roll(raw: str) -> str:
    """Normalize SL20260142 / SL-2026-0142 / sl 2026 0142 → SL-2026-0142."""
    compact = re.sub(r"[\s]+", "", raw.strip().upper().replace("_", "-"))
    compact = compact.replace("SL-", "SL").replace("SL", "SL-", 1) if not compact.startswith("SL-") else compact
    m = re.match(r"SL-?(\d{4})-?(\d{3,4})$", compact.replace(" ", ""))
    if m:
        return f"SL-{m.group(1)}-{m.group(2)}"
    m2 = _ROLL_CANON_RE.search(raw)
    if m2:
        return f"SL-{m2.group(1)}-{m2.group(2)}"
    return raw.strip().upper()


def _extract_roll(text: str) -> str | None:
    m = _ROLL_RE.search(text)
    if not m:
        # bare digits pattern inside SL-like tokens
        m2 = re.search(r"\bSL[-\s]?\d{6,10}\b", text, re.I)
        if not m2:
            return None
        return _canon_roll(m2.group(0))
    return _canon_roll(m.group(0))


def _extract_name(text: str, roll: str | None) -> str:
    """Pull a person-name out of the message after removing the roll number."""
    scrubbed = text
    if roll:
        scrubbed = re.sub(re.escape(roll), " ", scrubbed, flags=re.I)
        # also strip raw roll fragments
        scrubbed = _ROLL_RE.sub(" ", scrubbed)
    scrubbed = re.sub(r"[^\w\s,'-]", " ", scrubbed)
    scrubbed = re.sub(
        r"\b(hello|hi|hey|my name is|name is|i am|i'm|is|am|roll|number|"
        r"registration|student|please|kindly|the|my|me|for|to|get|courses?|"
        r"and|&)\b",
        " ",
        scrubbed,
        flags=re.I,
    )
    words = [w for w in scrubbed.split() if len(w) > 1]
    if not words:
        return ""
    # Keep up to 3 tokens (First Middle Last)
    return " ".join(words[:3]).strip()


def match_profile(name: str, roll: str | None) -> tuple[str, StudentProfile] | None:
    """Match free-text name + optional roll number to a fixture profile (FR-12)."""
    roll_c = _canon_roll(roll) if roll else None
    name_l = " ".join(name.split()).lower()

    # 1) roll number is unique and authoritative
    if roll_c:
        for key, profile in PROFILES.items():
            if _canon_roll(profile.roll_no) == roll_c:
                return key, profile

    # 2) full name match
    if name_l:
        for key, profile in PROFILES.items():
            if profile.name.lower() == name_l:
                return key, profile

        # 3) first + last
        for key, profile in PROFILES.items():
            parts = profile.name.lower().split()
            if len(parts) >= 2 and name_l == " ".join(parts[:2]):
                return key, profile

        # 4) unique first name only
        first = name_l.split()[0]
        hits = [(k, p) for k, p in PROFILES.items() if p.name.split()[0].lower() == first]
        if len(hits) == 1:
            return hits[0]

        # 5) unique last name only
        last = name_l.split()[-1]
        hits = [(k, p) for k, p in PROFILES.items() if p.name.split()[-1].lower() == last]
        if len(hits) == 1:
            return hits[0]

    return None


def _known_students_hint() -> str:
    lines = [f"- {p.name} · `{p.roll_no}`" for p in PROFILES.values()]
    return "\n".join(lines)


async def _activate_profile(profile_key: str) -> StudentProfile:
    """Build agent + attach profile ONCE after identity is known (FR-12)."""
    profile: StudentProfile = PROFILES[profile_key]
    agent = build_desk_agent(profile)
    cl.user_session.set("profile_key", profile_key)
    cl.user_session.set("profile", profile)
    cl.user_session.set("agent", agent)
    cl.user_session.set("phase", _READY)
    cl.user_session.set("history", [])
    first = profile.name.split()[0]
    course = profile.course_id
    await cl.Message(
        content=(
            f"yep — you're in, **{profile.name}** 🎓\n\n"
            f"i've got your course `{course}` loaded "
            f"(tier `{profile.tier}`, `{profile.roll_no}`).\n\n"
            f"hey {first} — what do you need? "
            "assignments, schedules, policies, careers… just talk to me."
        )
    ).send()
    return profile


@cl.on_chat_start
async def on_chat_start() -> None:
    """Bootstrap once; ask for name + roll number (no profile dropdown)."""
    try:
        bootstrap()
    except RuntimeError as exc:
        await cl.Message(
            content=(
                "hmm — couldn't start your study buddy right now. "
                f"mind checking your API key and refreshing?\n\n> {exc}"
            )
        ).send()
        return

    conversation_id = uuid.uuid4().hex
    cl.user_session.set("conversation_id", conversation_id)
    cl.user_session.set("phase", _AWAITING_IDENTITY)
    cl.user_session.set("profile", None)
    cl.user_session.set("agent", None)
    cl.user_session.set("profile_key", None)
    cl.user_session.set("history", [])

    await cl.Message(content=WELCOME_PROMPT).send()


async def _handle_identity(raw: str) -> bool:
    """Parse name/roll from the first message; activate profile. True if ready after."""
    text = (raw or "").strip()
    if not text:
        await cl.Message(
            content=(
                "i still need your **name** and **roll number** — "
                "something like `Abdullah Ahmed · SL-2026-0142`."
            )
        ).send()
        return False

    roll = _extract_roll(text)
    name = _extract_name(text, roll)
    hit = match_profile(name, roll)

    if hit is None:
        await cl.Message(
            content=(
                "hmm, couldn't match that to a student yet 😅\n\n"
                "try both together, e.g.\n"
                "`Abdullah Ahmed · SL-2026-0142`\n\n"
                "here's who i know right now:\n"
                f"{_known_students_hint()}"
            )
        ).send()
        return False

    await _activate_profile(hit[0])
    return True


@cl.on_message
async def on_message(message: cl.Message) -> None:
    """Identity gate first; then await the run (never run_sync); reuse session agent/history."""
    phase = cl.user_session.get("phase")
    agent = cl.user_session.get("agent")
    profile = cl.user_session.get("profile")

    if phase == _AWAITING_IDENTITY or agent is None or profile is None:
        await _handle_identity(message.content or "")
        return

    history: list = cl.user_session.get("history") or []
    conversation_id = cl.user_session.get("conversation_id") or uuid.uuid4().hex

    if history:
        run_input = [*history, {"role": "user", "content": message.content}]
    else:
        run_input = message.content

    try:
        result = await Runner.run(  # await — not run_sync / not fire-and-forget
            agent,
            input=run_input,
            context=profile,
            max_turns=MAX_TURNS,
            hooks=AuditRunHooks(RECORDER),
            run_config=conversation_run_config(conversation_id),
        )
    except InputGuardrailTripwireTriggered:
        await cl.Message(content=POLITE_REFUSAL).send()
        return
    except MaxTurnsExceeded:
        await cl.Message(
            content=(
                "oops, that one ran a bit long and I hit my turn limit "
                f"({MAX_TURNS}) 😅 mind making it a little shorter or more specific? "
                "i'd love to help."
            )
        ).send()
        return

    # Persist history for the next turn in this session only.
    cl.user_session.set("history", result.to_input_list())

    final = result.final_output

    if isinstance(final, Ticket):
        body = _ticket_chat_body(final)
    else:
        body = str(final)

    await cl.Message(content=body).send()


def _ticket_chat_body(final: Ticket) -> str:
    """Render Ticket as a personal chat reply — not a third-person staff note."""
    summary = (final.summary or "").strip()
    next_step = (final.next_step or "").strip()

    # If the model still writes an audit note, keep only a personal/factual tail.
    if summary and _looks_like_third_person_note(summary):
        if " and " in summary:
            tail = summary.split(" and ", 1)[-1].strip()
            if tail and _looks_like_chat_reply(tail):
                summary = tail
            else:
                summary = ""
        else:
            summary = ""

    parts: list[str] = []
    if summary:
        parts.append(summary)
    if next_step and next_step.lower() not in (summary or "").lower():
        parts.append(f"**next:** {next_step}")

    if final.escalate:
        parts.append("_looping in a human teammate — hang tight 🤝_")
    elif final.resolved and not parts:
        parts.append("yep, got you ✨")

    return "\n\n".join(parts) if parts else "hm, didn't catch that — try again?"


_THIRD_PERSON_RE = re.compile(
    r"^(?:[A-Z][a-z]+ (?:asked|learned|wants|wanted)|"
    r"the student (?:asked|learned|wants|wanted)|"
    r"they (?:asked|learned)|this ticket)\b",
    re.I,
)

_CHAT_REPLY_RE = re.compile(
    r"^(?:you|your|yours|we|let'?s|i|i'?m|here|sure|okay|ok|yes|no|"
    r"tool-calling|first |etl |warehouse |prompt |capstone |"
    r"a[0-9]|d[0-9]|p[0-9]|m[0-9])\b",
    re.I,
)


def _looks_like_third_person_note(text: str) -> bool:
    return bool(_THIRD_PERSON_RE.match(text.strip()))


def _looks_like_chat_reply(text: str) -> str | bool:
    """Tail after an audit note is only kept if it talks TO the student (or lists facts)."""
    return bool(_CHAT_REPLY_RE.match(text.strip()))


def main() -> None:
    """Local entry: `python app.py` is not the server — use chainlit run app.py."""
    require_openai_api_key()
    print("Run: uv run chainlit run app.py --port 8000")


if __name__ == "__main__":
    main()
