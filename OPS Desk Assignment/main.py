"""Phase 1–3 entry point — FR-1 async Desk, FR-5..FR-13 run controls."""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid

from agents import InputGuardrailTripwireTriggered, MaxTurnsExceeded, Runner, RunConfig

from ops_desk.agent import build_desk_agent
from ops_desk.audit import AuditRunHooks, RECORDER
from ops_desk.bootstrap import bootstrap
from ops_desk.config import MAX_TURNS, require_openai_api_key
from ops_desk.guardrails import POLITE_REFUSAL
from ops_desk.profile import StudentProfile
from ops_desk.ticket import Ticket
from ops_desk.tracing_setup import conversation_run_config
from test_profiles import PROFILES


def describe_result(result: object) -> str:
    """Print typed Ticket (FR-7) and name the agent that answered (FR-5)."""
    last = getattr(result, "last_agent", None)
    last_name = getattr(last, "name", "?") if last else "?"
    final = result.final_output  # type: ignore[attr-defined]

    lines: list[str] = []
    request_id = getattr(result, "request_id", None)
    elapsed_ms = getattr(result, "elapsed_ms", None)
    if request_id:
        lines.append(f"request_id={request_id}")
    if elapsed_ms is not None:
        lines.append(f"elapsed_ms={elapsed_ms}")

    if isinstance(final, Ticket):
        lines.extend(
            [
                f"answering_agent={last_name}",
                f"final_output_type={type(final).__name__}",
                f"category={final.category}",
                f"summary={final.summary}",
                f"next_step={final.next_step}",
                f"resolved={final.resolved}",
                f"escalate={final.escalate}",
            ]
        )
        lines.append("branch=RESOLVED" if final.resolved else "branch=UNRESOLVED")
        if final.escalate:
            lines.append("branch=ESCALATE")
        return "\n".join(lines)

    return "\n".join(
        [
            *lines,
            f"answering_agent={last_name}",
            f"final_output_type={type(final).__name__}",
            str(final),
        ]
    )


async def run_desk(
    question: str,
    profile: StudentProfile,
    conversation_id: str | None = None,
) -> str:
    """One Desk turn: guardrail → prompt → stamped run + audit hooks + one-trace config."""
    from ops_desk.prompts import build_system_prompt

    instructions = build_system_prompt(profile)
    print("\n=== resolved system prompt (before model call) ===")
    print(instructions)
    print("=== end resolved prompt ===\n")

    agent = build_desk_agent(profile)
    conv_id = conversation_id or uuid.uuid4().hex
    run_config: RunConfig = conversation_run_config(conv_id)
    hooks = AuditRunHooks(RECORDER)

    try:
        result = await Runner.run(
            agent,
            input=question,
            context=profile,  # local context (FR-3)
            max_turns=MAX_TURNS,  # explicit ceiling (FR-9 / NFR-2)
            hooks=hooks,  # FR-10 run-level timeline
            run_config=run_config,  # FR-13 one conversation → one trace group
        )
    except InputGuardrailTripwireTriggered:
        print("[guardrail] course-scope tripwire — Desk model not called")
        return POLITE_REFUSAL
    except MaxTurnsExceeded:
        return (
            f"oops, that ran a little long and I hit my turn limit ({MAX_TURNS}) 😅 "
            "mind making it shorter or more specific?"
        )

    text = describe_result(result)
    # FR-10 demo: ordered agents in this conversation
    order = RECORDER.agent_order()
    if order:
        text += f"\ntimeline_agents={'>'.join(order)}"
    text += f"\naudit_file={RECORDER.path}"
    return text


async def amain(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Saylani Student Ops Desk")
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILES),
        default="regular",
        help="Which fixture profile to attach as local context",
    )
    parser.add_argument(
        "question",
        nargs="*",
        help="Question for the Desk (prompted interactively if omitted)",
    )
    args = parser.parse_args(argv)

    try:
        bootstrap()  # NFR-1 key + FR-11 runner + FR-13 tracing (once)
    except RuntimeError as exc:
        print(f"STARTUP ERROR: {exc}", file=sys.stderr)
        return 1

    profile = PROFILES[args.profile]
    question = " ".join(args.question).strip()
    if not question:
        question = input("Ask the Ops Desk: ").strip()
    if not question:
        print("No question provided.", file=sys.stderr)
        return 1

    answer = await run_desk(question, profile)
    print(answer)
    return 0


def main() -> None:
    """Sync entry: async function driven by asyncio.run (FR-1)."""
    raise SystemExit(asyncio.run(amain()))


if __name__ == "__main__":
    main()
