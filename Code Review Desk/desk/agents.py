from pathlib import Path

from agents import Agent, ModelSettings, function_tool, handoff

from desk.context import ReviewContext
from desk.findings import Finding, RemediationProposal
from desk.guardrails import build_secret_guardrail
from desk.prompts import (
    build_instructions,
    build_security_instructions,
    build_style_instructions,
    build_test_instructions,
)

RULESETS_DIR = Path(__file__).resolve().parent.parent / "rulesets"


def model_usable_error(context, exc: Exception) -> str:
    return f"error: tool call failed ({type(exc).__name__}: {exc}). Continue with available information."


def build_read_ruleset_tool(context: ReviewContext):
    @function_tool(failure_error_function=model_usable_error)
    def read_ruleset() -> str:
        """Load the active ruleset for this review."""
        try:
            header = (
                f"language={context.language} "
                f"ruleset_id={context.ruleset_id} "
                f"strictness={context.strictness}\n"
            )
            path = RULESETS_DIR / f"{context.ruleset_id}.md"
            if not path.exists():
                return (
                    f"{header}"
                    f"error: ruleset not found: {context.ruleset_id}. "
                    f"Continue with language={context.language} guidance only."
                )
            return header + path.read_text(encoding="utf-8")
        except Exception as e:
            return f"error: could not read ruleset ({type(e).__name__}: {e}). Continue with available information."

    return read_ruleset


def build_tool(context: ReviewContext):
    return build_read_ruleset_tool(context)


def build_reviewer(
    context: ReviewContext,
    *,
    secrets: list[str] | None = None,
    force_ruleset_tool: bool = False,
    instructions: str | None = None,
    name: str = "BaseReviewer",
) -> Agent:
    model_settings = (
        ModelSettings(tool_choice="read_ruleset")
        if force_ruleset_tool
        else ModelSettings()
    )
    guardrails = [build_secret_guardrail(secrets or [])] if secrets is not None else []
    kwargs: dict = {
        "name": name,
        "instructions": instructions or build_instructions(context),
        "model": "gpt-4o-mini",
        "tools": [build_read_ruleset_tool(context)],
        "output_type": list[Finding],
        "model_settings": model_settings,
    }
    if guardrails:
        kwargs["output_guardrails"] = guardrails
    return Agent(**kwargs)


def build_security_reviewer(
    context: ReviewContext,
    *,
    secrets: list[str] | None = None,
    remediation: Agent | None = None,
) -> Agent:
    base = build_reviewer(context, secrets=secrets)
    cloned = base.clone(
        name="SecurityReviewer",
        instructions=build_security_instructions(context),
        model_settings=ModelSettings(tool_choice="read_ruleset"),
    )
    if remediation is not None:
        return cloned.clone(handoffs=[handoff(remediation)])
    return cloned


def build_test_reviewer(context: ReviewContext, *, secrets: list[str] | None = None) -> Agent:
    base = build_reviewer(context, secrets=secrets)
    return base.clone(
        name="TestReviewer",
        instructions=build_test_instructions(context),
        model_settings=ModelSettings(tool_choice="read_ruleset"),
    )


def build_style_reviewer(context: ReviewContext, *, secrets: list[str] | None = None) -> Agent:
    base = build_reviewer(context, secrets=secrets)
    return base.clone(
        name="StyleReviewer",
        instructions=build_style_instructions(context),
        model_settings=ModelSettings(tool_choice="read_ruleset"),
    )


def build_remediation_agent(context: ReviewContext, *, secrets: list[str] | None = None) -> Agent:
    guardrails = [build_secret_guardrail(secrets or [])] if secrets is not None else []
    return Agent(
        name="Remediation",
        instructions=(
            "You are the Remediation agent. You receive a critical security finding "
            "and propose a minimal, safe patch. Return a RemediationProposal with "
            "finding, patch, and rationale. Never echo secrets from the diff."
        ),
        model="gpt-4o-mini",
        output_type=RemediationProposal,
        output_guardrails=guardrails,
    )


def build_merge_agent(context: ReviewContext, *, secrets: list[str] | None = None) -> Agent:
    guardrails = [build_secret_guardrail(secrets or [])] if secrets is not None else []
    return Agent(
        name="Merge",
        instructions=(
            "You are the Merge agent. Combine reviewer findings into one report: "
            "deduplicate identical findings and order by severity "
            "(critical, major, minor). Return list[Finding]."
        ),
        model="gpt-4o-mini",
        output_type=list[Finding],
        output_guardrails=guardrails,
    )


def build_merge_tool(merge_agent: Agent):
    return merge_agent.as_tool(
        tool_name="merge_findings",
        tool_description="Merge reviewer findings into one report ordered by severity",
    )


def build_desk_host(
    context: ReviewContext,
    merge_agent: Agent,
    *,
    secrets: list[str] | None = None,
) -> Agent:
    """Host agent that keeps the conversation and exposes Merge as a tool (FR-6)."""
    guardrails = [build_secret_guardrail(secrets or [])] if secrets is not None else []
    return Agent(
        name="Desk",
        instructions=(
            "You are the Code Review Desk host. You receive JSON findings from the "
            "three reviewers. Call merge_findings exactly once with that payload to "
            "produce one ordered, deduplicated report. Return list[Finding]."
        ),
        model="gpt-4o-mini",
        tools=[build_merge_tool(merge_agent)],
        output_type=list[Finding],
        output_guardrails=guardrails,
    )
