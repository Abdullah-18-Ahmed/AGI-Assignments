import re

from agents import GuardrailFunctionOutput, OutputGuardrail, output_guardrail

from desk.findings import Finding, MergedReport

SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(
        r"(?i)(?:api[_-]?key|secret|token|password|passwd|pwd)"
        r"\s*[:=]\s*['\"]?([^\s'\"]{8,})"
    ),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{16,}"),
]


def extract_secrets(diff_text: str) -> list[str]:
    found: list[str] = []
    for pattern in SECRET_PATTERNS:
        for match in pattern.finditer(diff_text):
            if match.groups():
                for group in match.groups():
                    if group:
                        found.append(group)
            else:
                found.append(match.group(0))
    seen: set[str] = set()
    unique: list[str] = []
    for secret in found:
        if secret not in seen:
            seen.add(secret)
            unique.append(secret)
    return unique


def _output_to_text(output: object) -> str:
    if isinstance(output, str):
        return output
    if isinstance(output, list):
        parts: list[str] = []
        for item in output:
            if isinstance(item, Finding):
                parts.append(item.message)
            elif isinstance(item, dict):
                parts.append(str(item.get("message", item)))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    if isinstance(output, MergedReport):
        return "\n".join(f.message for f in output.findings) + "\n" + output.summary
    if hasattr(output, "model_dump"):
        return str(output.model_dump())
    return str(output)


def build_secret_guardrail(secrets: list[str]) -> OutputGuardrail:
    lowered = [s for s in secrets if s]

    @output_guardrail(name="secret_leak_guardrail")
    def secret_leak_guardrail(context, agent, output) -> GuardrailFunctionOutput:
        try:
            text = _output_to_text(output)
        except Exception as e:
            return GuardrailFunctionOutput(
                output_info={"error": f"could not inspect output: {e}"},
                tripwire_triggered=False,
            )

        for secret in lowered:
            if secret and secret in text:
                return GuardrailFunctionOutput(
                    output_info={"leaked": True, "reason": "secret from diff appears in output"},
                    tripwire_triggered=True,
                )

        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                return GuardrailFunctionOutput(
                    output_info={"leaked": True, "reason": "credential-like pattern in output"},
                    tripwire_triggered=True,
                )

        return GuardrailFunctionOutput(output_info=None, tripwire_triggered=False)

    return secret_leak_guardrail
