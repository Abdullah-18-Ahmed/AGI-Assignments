"""Live chat smoke: assignment / career / policy / scholarship / handoff paths."""
from __future__ import annotations

import asyncio
import re

from main import run_desk
from ops_desk.bootstrap import bootstrap
from test_profiles import PROFILES, REGULAR_CALM, SCHOLARSHIP, REGULAR_TERSE


THIRD_PERSON = re.compile(
    r"\b(they asked|the student asked|he asked|she asked|abdullah asked|"
    r"bilal asked|hina asked|the student learned|they learned)\b",
    re.I,
)
FACT_HINTS = {
    "assignment": re.compile(r"\b(a1|a3|d1|d2|p1|m1|due|2026-|tool-calling|first coded|etl|warehouse|prompt eval|capstone)\b", re.I),
    "career": re.compile(r"\b(cv|intern|interview|resume|job|career|hiring)\b", re.I),
    "policy": re.compile(r"\b(late|penalty|attendance|48 hours|policy|stipend|scholarship)\b", re.I),
}


async def one(label: str, question: str, profile_key: str, kind: str) -> None:
    profile = PROFILES[profile_key]
    print("\n" + "=" * 72)
    print(f"CASE {label} | profile={profile_key} | q={question!r}")
    text = await run_desk(question, profile, conversation_id=f"smoke-{label}")
    print(text)
    # analyze final-looking summary lines
    summary_lines = [
        ln[len("summary="):]
        for ln in text.splitlines()
        if ln.startswith("summary=")
    ]
    summary = summary_lines[0] if summary_lines else text
    third = bool(THIRD_PERSON.search(summary))
    fact = bool(FACT_HINTS[kind].search(summary)) if kind in FACT_HINTS else True
    agent = next((ln for ln in text.splitlines() if ln.startswith("answering_agent=")), "")
    print(f"CHECK third_person={third} fact_in_summary={fact} {agent}")
    if third:
        print("FAIL third-person summary")
    if not fact:
        print("FAIL missing facts for kind=" + kind)


async def amain() -> int:
    bootstrap()
    cases = [
        ("assign-short", "what are the assignments", "regular", "assignment"),
        ("assign-deep", "when is assignment a1 due and what do I submit?", "regular", "assignment"),
        ("career", "help me with my CV for internships after this bootcamp", "regular", "career"),
        ("policy", "what's the late submission policy for my course?", "regular", "policy"),
        ("sch-benefits", "what scholarship benefits do I get?", "scholarship", "policy"),
        ("terse-assign", "list my open assignments", "terse", "assignment"),
    ]
    fails = 0
    for label, q, key, kind in cases:
        try:
            await one(label, q, key, kind)
        except Exception as exc:
            fails += 1
            print(f"ERROR {label}: {type(exc).__name__}: {exc}")
    print("\nDONE fails=", fails)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(amain()))
