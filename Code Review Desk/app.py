import json
import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

if not os.getenv("OPENAI_API_KEY"):
    raise SystemExit(
        "OPENAI_API_KEY is missing. Copy .env.example to .env and set your key, then start the app again."
    )

import chainlit as cl

from desk import (
    Finding,
    ReviewContext,
    register_ledger,
    run_pipeline,
)

register_ledger()

SEVERITY_EMOJI = {"critical": "🔴", "major": "🟠", "minor": "🟡"}


def _finding_line(f: Finding) -> str:
    emoji = SEVERITY_EMOJI.get(f.severity, "⚪")
    return f"{emoji} **{f.severity}** `{f.file}:{f.line}` — {f.message}"


def render_report(outcome) -> str:
    if not outcome.findings:
        base = f"**Status:** {outcome.status} — no findings.\n\n{outcome.message}"
    else:
        lines = [f"**Status:** {outcome.status}", "", "## Findings", ""]
        for f in outcome.findings:
            lines.append(_finding_line(f))
        lines.append("")
        lines.append(f"_{outcome.message}_")
        base = "\n".join(lines)

    if outcome.remediation is not None:
        r = outcome.remediation
        rmd = getattr(r, "model_dump", lambda: r)()
        base += "\n\n## Remediation proposal\n\n```json\n" + json.dumps(rmd, indent=2) + "\n```"

    if outcome.metrics_footer:
        base += "\n" + outcome.metrics_footer

    if outcome.trace_id:
        base += f"\n\n`trace_id: {outcome.trace_id}`\n"

    return base


@cl.on_chat_start
async def on_chat_start() -> None:
    await cl.Message(
        content=(
            "## Code Review Desk\n\n"
            "Paste a unified diff (or set `diff_path` / drop a file path in chat) "
            "and I'll run Security, Test, and Style reviewers in parallel.\n\n"
            "Optional line commands:\n"
            "- `/repo <name>` — set ReviewContext.repo\n"
            "- `/lang <language>` — set ReviewContext.language\n"
            "- `/ruleset <id>` — set ReviewContext.ruleset_id\n"
            "- `/strictness <level>` — normal | strict"
        )
    ).send()

    cl.user_session.set(
        "review_context",
        ReviewContext(repo="adhoc", language="python", ruleset_id="py-standard"),
    )
    cl.user_session.set("findings_by_agent", {})


def _parse_context_command(text: str, ctx: ReviewContext) -> ReviewContext | None:
    parts = text.strip().split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        return None
    cmd, value = parts[0], parts[1].strip()
    data = {
        "repo": ctx.repo,
        "language": ctx.language,
        "ruleset_id": ctx.ruleset_id,
        "strictness": ctx.strictness,
    }
    if cmd == "/repo":
        data["repo"] = value
    elif cmd == "/lang":
        data["language"] = value
    elif cmd == "/ruleset":
        data["ruleset_id"] = value
    elif cmd == "/strictness":
        if value not in ("normal", "strict"):
            return None
        data["strictness"] = value
    else:
        return None
    return ReviewContext(**data)


async def _on_findings(agent_name: str, findings: list[Finding]) -> None:
    store: dict = cl.user_session.get("findings_by_agent") or {}
    store[agent_name] = findings
    cl.user_session.set("findings_by_agent", store)

    if not findings:
        await cl.Message(content=f"**{agent_name}:** no findings").send()
        return
    body = "\n".join(_finding_line(f) for f in findings)
    await cl.Message(content=f"**{agent_name}** ({len(findings)})\n\n{body}").send()


@cl.on_message
async def on_message(message: cl.Message) -> None:
    text = (message.content or "").strip()
    if not text:
        await cl.Message(content="Paste a diff or provide a `diff_path`.").send()
        return

    ctx: ReviewContext = cl.user_session.get(
        "review_context"
    ) or ReviewContext(repo="adhoc", language="python", ruleset_id="py-standard")

    if text.startswith("/"):
        updated = _parse_context_command(text, ctx)
        if updated is not None:
            cl.user_session.set("review_context", updated)
            await cl.Message(content=f"Context updated: `{updated}`").send()
            return
        known = {"/repo", "/lang", "/ruleset", "/strictness"}
        first = text.split()[0]
        if first in known:
            if first == "/strictness":
                await cl.Message(
                    content="Usage: `/strictness normal` or `/strictness strict`"
                ).send()
            else:
                await cl.Message(content=f"Usage: `{first} <value>`").send()
            return
        await cl.Message(content=f"Unknown command: `{first}`").send()
        return

    diff_path = text
    if not (text.lstrip().startswith(("diff --git", "--- ", "+++ ")) or text.endswith((".diff", ".patch"))):
        candidate = Path(text)
        if candidate.exists() and candidate.is_file():
            diff_path = str(candidate)
        else:
            with tempfile.NamedTemporaryFile(
                "w", suffix=".diff", delete=False, encoding="utf-8"
            ) as f:
                f.write(text)
                diff_path = f.name
    elif not Path(diff_path).exists():
        with tempfile.NamedTemporaryFile(
            "w", suffix=".diff", delete=False, encoding="utf-8"
        ) as f:
            f.write(text)
            diff_path = f.name

    status_msg = cl.Message(content=f"Reviewing `{diff_path}` …")
    await status_msg.send()

    try:
        outcome = await run_pipeline(
            diff_path,
            ctx,
            on_findings=_on_findings,
            enable_otel=True,
        )
    except Exception as e:
        await cl.Message(content=f"Pipeline error: `{type(e).__name__}: {e}`").send()
        return

    cl.user_session.set("last_outcome", outcome)
    report = render_report(outcome)
    await cl.Message(content=report).send()


if __name__ == "__main__":
    cl.run()
