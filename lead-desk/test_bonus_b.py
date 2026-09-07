import asyncio
import json

from agents import Runner

import main as leaddesk

SAMPLE = {
    "id": 7,
    "message": (
        "Hi, I need a full React dashboard for our SaaS analytics platform. "
        "Budget is $15,000. Can you start next week? Please send me a proposal."
    ),
    "platform": "email",
}

UNVERIFIED_PROFILE = leaddesk.profile.model_copy(update={"verified": False})


def tool_names(agent) -> list[str]:
    return [t.name for t in agent.tools]


async def run(agent, current_profile, lead):
    for attempt in range(3):
        try:
            return await Runner.run(
                agent,
                f"[Client #{lead['id']} via {lead['platform']}]: {lead['message']}",
                context=current_profile,
            )
        except Exception as exc:
            print(f"  (attempt {attempt + 1} failed: {type(exc).__name__}: {str(exc)[:120]})")
            await asyncio.sleep(5)
    return None


async def main():
    print("=" * 70)
    print("PROFILE VERIFIED = FALSE  (send_proposal must be OMITTED)")
    print("=" * 70)
    agent_false = leaddesk.build_agent(UNVERIFIED_PROFILE)
    print("tool names:", tool_names(agent_false))
    print("send_proposal present:", "send_proposal" in tool_names(agent_false))

    result = await run(agent_false, UNVERIFIED_PROFILE, SAMPLE)
    if result is not None:
        triage = result.final_output
        print("executed -> final_output type:", type(triage).__name__)
        print("priority:", triage.priority, "| budget_pkr:", triage.budget_pkr)

    print("\n" + "=" * 70)
    print("PROFILE VERIFIED = TRUE  (send_proposal must be PRESENT)")
    print("=" * 70)
    agent_true = leaddesk.build_agent(leaddesk.profile)
    print("tool names:", tool_names(agent_true))
    print("send_proposal present:", "send_proposal" in tool_names(agent_true))
    send_proposal_tool = next(t for t in agent_true.tools if t.name == "send_proposal")
    print("send_proposal schema:", json.dumps(send_proposal_tool.params_json_schema))

    result = await run(agent_true, leaddesk.profile, SAMPLE)
    if result is not None:
        triage = result.final_output
        print("executed -> final_output type:", type(triage).__name__)
        print("priority:", triage.priority, "| budget_pkr:", triage.budget_pkr)

    if leaddesk.PROPOSALS_PATH.exists():
        print("\nproposals.json:", json.dumps(json.loads(leaddesk.PROPOSALS_PATH.read_text()), indent=2))


if __name__ == "__main__":
    asyncio.run(main())