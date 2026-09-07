import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Literal, Optional

from dotenv import load_dotenv
from openai import AsyncOpenAI, RateLimitError
from pydantic import BaseModel

from agents import Agent, OpenAIChatCompletionsModel, Runner, RunContextWrapper, function_tool

load_dotenv()


class FreelancerProfile(BaseModel):
    name: str
    min_rate_pkr_hour: float
    skills: dict[str, int]
    hours_free_per_week: dict[str, int]
    verified: bool


class LeadTriage(BaseModel):
    intent: str
    budget_pkr: Optional[int] = None
    red_flags: list[str] = []
    priority: Literal["high", "medium", "low"]
    suggested_reply: str


_LIE_PATTERNS = [
    re.compile(
        r"\b(li[ea]|lies|lied|lying|liar|fake|faker\w*|fabricat\w*|falsif\w*"
        r"|pretend\w*|overstat\w*|exaggerat\w*|embellish\w*|inflat\w*|fudge\w*"
        r"|puff\s*up|boast\w*|massag\w*|claim\w*|invent\w*|phony|unearned)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\bmake\s?up\w*\b", re.IGNORECASE),
    re.compile(r"\bsay\s+(?:you|i)\s+have\b", re.IGNORECASE),
    re.compile(r"\b(add|gain|grant)\b[^.\n]{0,40}\byears?\b[^.\n]{0,20}\b(experience|resume|cv)\b",
               re.IGNORECASE),
    re.compile(r"\byears?\b[^.\n]{0,20}\b(add|claim|pretend|fake)\b", re.IGNORECASE),
]

_CREDENTIAL_PATTERN = re.compile(
    r"\b(years?|experience|resume|cv|curriculum vitae|portfolio|work history|job history"
    r"|employment|worked at|degree|degrees|certification\w*|reference\w*|award\w+|accolade\w+)\b",
    re.IGNORECASE,
)


def check_input_guardrail(message: str) -> bool:
    """Rule-based pre-filter returning True if the message asks to lie, overstate,
    or fabricate work experience / credentials (e.g. claiming unearned years of
    experience). No LLM or API calls are made by this check."""
    if not _CREDENTIAL_PATTERN.search(message):
        return False
    return any(pattern.search(message) for pattern in _LIE_PATTERNS)


profile = FreelancerProfile(
    name="Abdullah Ahmed",
    min_rate_pkr_hour=2500.0,
    skills={
        "react": 150,
        "python": 130,
        "node": 140,
        "fastapi": 145,
        "nextjs": 155,
        "css": 90,
        "figma": 110,
        "devops": 160,
    },
    hours_free_per_week={
        "week 1": 40,
        "week 2": 30,
        "week 3": 0,
        "week 4": 20,
    },
    verified=True,
)


@function_tool
def lookup_rate_card(ctx: RunContextWrapper[FreelancerProfile], skill: str) -> str:
    """Look up the hourly rate for a given skill or technology.

    Call this tool BEFORE discussing pricing or quoting any cost to a client.
    If the skill is not found in the rate card, state that the skill is unknown
    and you cannot provide a rate for it.

    Args:
        skill: The technology or skill name (e.g. 'python', 'react', 'node').
    """
    skill_lower = skill.lower().strip()
    rate = ctx.context.skills.get(skill_lower)
    if rate is not None:
        return f"${rate}/hr"
    return f"Unknown skill: '{skill}'. No rate available."


@function_tool
def check_availability(ctx: RunContextWrapper[FreelancerProfile], week: str) -> str:
    """Check freelancer availability for a given week.

    Use this when a client asks about scheduling, timelines, or start dates.

    Args:
        week: The week to check (e.g. 'week 1', 'week 2', 'week 3', 'week 4').
    """
    week_lower = week.lower().strip()
    hours = ctx.context.hours_free_per_week.get(week_lower)
    if hours is None:
        valid = ", ".join(ctx.context.hours_free_per_week.keys())
        return f"Week '{week}' not found. Valid options: {valid}"
    if hours <= 0:
        return f"{week.capitalize()}: not available (0 hrs free)"
    return f"{week.capitalize()}: available ({hours} hrs free)"


openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise ValueError("OPENAI_API_KEY is not set in .env")

client = AsyncOpenAI(api_key=openai_api_key)

openai_model = os.getenv("OPENAI_MODEL", "gpt-4o")

model = OpenAIChatCompletionsModel(
    model=openai_model,
    openai_client=client,
)

PROPOSALS_PATH = Path(__file__).parent / "proposals.json"


@function_tool
def send_proposal(ctx: RunContextWrapper[FreelancerProfile], lead_id: int) -> str:
    """Send a proposal to a qualified client for the given lead id.

    Only present when the freelancer profile is verified. Call this when an
    inbound lead should receive a proposal. Records the proposal on disk.

    Args:
        lead_id: Numeric id of the lead to send a proposal for.
    """
    record = {
        "lead_id": lead_id,
        "freelancer": ctx.context.name,
        "status": "proposal_sent",
    }
    proposals = []
    if PROPOSALS_PATH.exists():
        proposals = json.loads(PROPOSALS_PATH.read_text())
    proposals.append(record)
    PROPOSALS_PATH.write_text(json.dumps(proposals, indent=2))
    return f"Proposal recorded for lead #{lead_id}."


def build_agent(current_profile: FreelancerProfile) -> Agent:
    instructions = (
        "You are a freelance developer's lead qualification assistant. "
        "Triage each inbound client message and fill the LeadTriage fields:\n"
        "1. intent: classify as 'well-budgeted', 'revenue-share', 'vague', 'urgent', 'small', "
        "or 'aggressive deadline'.\n"
        "2. budget_pkr: If the client states a budget, convert it to PKR (approx 280 PKR per USD) "
        "and fill budget_pkr. If no budget is mentioned, leave it null.\n"
        "3. red_flags: List risk signals. You MUST include 'revenue-share offered' whenever the "
        "client offers equity/revenue-share instead of upfront payment. Also flag unrealistic "
        "deadlines (e.g. a full platform by Friday) or missing scope.\n"
        "4. priority: 'high' for well-budgeted or urgent paid work; 'medium' for small jobs or "
        "tight-but-possible deadlines; 'low' for revenue-share offers, vague/unscoped jobs, or "
        "aggressive deadlines.\n"
        "5. suggested_reply: Draft a short reply to the client.\n\n"
        "Tool rules:\n"
        "- You MUST call lookup_rate_card before discussing any pricing or cost. "
        "If the skill is not in the rate card, state that the skill is unknown and you cannot quote.\n"
        "- Call check_availability when a timeline or start date is mentioned.\n"
        "- The client message begins with '[Client #<id> via <platform>]': the lead id is the "
        "number after '#'."
    )
    if current_profile.verified:
        instructions += (
            "\n- This freelancer profile is verified, so the send_proposal tool is available. "
            "When a lead is qualified with priority 'high', call send_proposal with its lead id."
        )

    tools = [lookup_rate_card, check_availability]
    if current_profile.verified:
        tools.append(send_proposal)

    return Agent(
        name="Lead Desk",
        instructions=instructions,
        model=model,
        tools=tools,
        output_type=LeadTriage,
    )


agent = build_agent(profile)

LEADS_PATH = Path(__file__).parent / "leads.json"
SAVED_LEADS_PATH = Path(__file__).parent / "saved.json"


def save_lead(lead: dict) -> None:
    saved = []
    if SAVED_LEADS_PATH.exists():
        saved = json.loads(SAVED_LEADS_PATH.read_text())
    saved.append(lead)
    SAVED_LEADS_PATH.write_text(json.dumps(saved, indent=2))


async def main():
    print("=== lookup_rate_card JSON schema (context should be hidden) ===")
    print(json.dumps(lookup_rate_card.params_json_schema, indent=2))
    print("=== check_availability JSON schema (context should be hidden) ===")
    print(json.dumps(check_availability.params_json_schema, indent=2))

    leads = json.loads(LEADS_PATH.read_text())

    for lead in leads:
        message = lead["message"]

        if check_input_guardrail(message):
            print(
                f"\nLead #{lead['id']}: I'm sorry, but I can't assist with requests that ask "
                "to misrepresent or fabricate work experience or credentials. "
                "Stopping here — no AI call was made."
            )
            sys.exit(0)

        print(f"\n{'='*60}")
        print(f"LEAD #{lead['id']}  (via {lead['platform']})")
        print(f"{'='*60}")
        print(f"Message: {message}\n")

        result = await run_with_retry(agent, lead)

        if result is None:
            print("[Skipped: rate limit still exceeded after retries]")
            continue

        triage = result.final_output
        if triage is None:
            print("[No triage produced by model]")
            continue

        print(f"Intent: {triage.intent}")
        print(f"Budget PKR: {triage.budget_pkr}")
        print(f"Red flags: {triage.red_flags}")
        print(f"Priority: {triage.priority}")
        print(f"Suggested reply: {triage.suggested_reply}")

        if triage.priority == "high":
            print(f"GOOD LEAD: priority={triage.priority}, budget_pkr={triage.budget_pkr}")
            save_lead(lead)


async def run_with_retry(agent, lead, current_profile=None, max_attempts: int = 5):
    if current_profile is None:
        current_profile = profile
    for attempt in range(max_attempts):
        try:
            return await Runner.run(
                agent,
                f"[Client #{lead['id']} via {lead['platform']}]: {lead['message']}",
                context=current_profile,
            )
        except RateLimitError as exc:
            wait = (3 ** attempt) + attempt
            print(f"[Rate limited, retrying in {wait}s... ({exc.status_code})]")
            await asyncio.sleep(wait)
    return None


if __name__ == "__main__":
    asyncio.run(main())