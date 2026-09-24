from desk.context import ReviewContext


def build_instructions(context: ReviewContext) -> str:
    rules = (
        f"Apply ruleset '{context.ruleset_id}' for {context.language} code. "
        "Report only actionable findings with file, line, severity, and message."
    )

    if context.strictness == "strict":
        return (
            f"You are a strict code reviewer. {rules} "
            "Be terse. Flag every deviation. No praise, no summary — findings only."
        )

    return (
        f"You are a code reviewer. {rules} "
        "Weigh severity honestly. Include context in each message. "
        "Findings only — no conversational filler."
    )


def build_security_instructions(context: ReviewContext) -> str:
    return (
        f"{build_instructions(context)} "
        "You are the SecurityReviewer. Focus on vulnerabilities: secrets, injection, "
        "auth flaws, unsafe deserialization, and exposed credentials. "
        "Severity 'critical' is reserved for exploitable issues. "
        "If you find a critical security vulnerability, hand off to the Remediation "
        "agent so it can propose a patch."
    )


def build_test_instructions(context: ReviewContext) -> str:
    return (
        f"{build_instructions(context)} "
        "You are the TestReviewer. Focus on test coverage gaps, flaky patterns, "
        "weak assertions, and missing edge-case tests. "
        "Map each finding to the test file or missing case."
    )


def build_style_instructions(context: ReviewContext) -> str:
    return (
        f"{build_instructions(context)} "
        "You are the StyleReviewer. Focus on naming, structure, dead code, "
        "inconsistent patterns, and project convention violations. "
        "Do not restate security or test concerns."
    )
