import asyncio
import inspect
import time
from dataclasses import dataclass

import pytest
from agents import (
    Agent,
    FunctionTool,
    GuardrailFunctionOutput,
    MaxTurnsExceeded,
    ModelSettings,
    OutputGuardrail,
    OutputGuardrailResult,
    OutputGuardrailTripwireTriggered,
    RunConfig,
    RunResult,
    handoff,
)

from desk import (
    DiffError,
    Finding,
    MergedReport,
    ReviewContext,
    build_merge_agent,
    build_remediation_agent,
    build_reviewer,
    build_secret_guardrail,
    build_security_reviewer,
    build_style_reviewer,
    build_test_reviewer,
    extract_secrets,
    has_critical_finding,
    measure_wall_clock,
    merge_findings,
    run_reviewers_concurrently,
)
from desk.pipeline import run_reviewer


CTX = ReviewContext(repo="demo", language="python", ruleset_id="py-standard")
SAMPLE_DIFF = """\
diff --git a/src/app.py b/src/app.py
index 111..222 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,3 +1,4 @@
 import os
+API_KEY = "sk-live-abcdef1234567890secret"
 def main():
diff --git a/src/util.py b/src/util.py
index 333..444 100644
--- a/src/util.py
+++ b/src/util.py
@@ -1,2 +1,3 @@
 def helper():
+    password = "hunter2hunter2"
     return None
"""


# --- FR-5: concurrent clones via asyncio.gather ---

def test_fr5_three_named_reviewers():
    security = build_security_reviewer(CTX)
    test = build_test_reviewer(CTX)
    style = build_style_reviewer(CTX)
    assert security.name == "SecurityReviewer"
    assert test.name == "TestReviewer"
    assert style.name == "StyleReviewer"


def test_fr5_reviewers_are_clones_share_base_model():
    security = build_security_reviewer(CTX)
    test = build_test_reviewer(CTX)
    style = build_style_reviewer(CTX)
    for a in (security, test, style):
        assert a.model == "gpt-4o-mini"
        assert a.output_type == list[Finding]


def test_fr5_instructions_differ_per_reviewer():
    security = build_security_reviewer(CTX)
    test = build_test_reviewer(CTX)
    style = build_style_reviewer(CTX)
    assert "SecurityReviewer" in security.instructions
    assert "TestReviewer" in test.instructions
    assert "StyleReviewer" in style.instructions
    assert security.instructions != test.instructions != style.instructions


def test_fr5_gather_used_in_concurrent_runner():
    import desk.pipeline as pipeline_mod

    source = inspect.getsource(pipeline_mod)
    assert "asyncio.gather" in source


async def _fake_runner(agent, inp, **kwargs):
    await asyncio.sleep(0.3)
    fake = type("R", (), {})()
    fake.final_output = [
        Finding(file="a.py", line=1, severity="minor", message=f"finding from {agent.name}")
    ]
    fake.final_output_as = lambda cls: fake.final_output
    fake.last_agent = agent
    return fake


@pytest.mark.asyncio
async def test_fr5_parallel_wall_clock_faster_than_sequential():
    agents = [build_security_reviewer(CTX), build_test_reviewer(CTX), build_style_reviewer(CTX)]

    t0 = time.perf_counter()
    for a in agents:
        await _fake_runner(a, "diff")
    sequential_ms = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    result = await run_reviewers_concurrently(agents, "diff", CTX, runner=_fake_runner)
    concurrent_ms = result["elapsed_ms"]

    assert concurrent_ms < sequential_ms
    assert concurrent_ms < 500
    assert sequential_ms >= 850
    assert set(result["by_name"].keys()) == {
        "SecurityReviewer",
        "TestReviewer",
        "StyleReviewer",
    }


def test_fr5_measure_wall_clock_reports_speedup():
    agents = [build_security_reviewer(CTX), build_test_reviewer(CTX), build_style_reviewer(CTX)]
    stats = asyncio.run(
        measure_wall_clock(agents, "diff", CTX, runner=_fake_runner)
    )
    assert stats["sequential_ms"] >= stats["concurrent_ms"]
    assert stats["speedup"] >= 1.5


# --- FR-6: merge as_tool + remediation handoff ---

def test_fr6_merge_agent_exposed_as_tool():
    merge_agent = build_merge_agent(CTX)
    tool = merge_agent.as_tool(
        tool_name="merge_findings",
        tool_description="Merge reviewer findings into one report",
    )
    assert isinstance(tool, FunctionTool)
    assert tool.name == "merge_findings"
    schema = tool.params_json_schema or {}
    assert "input" in schema.get("properties", {})


def test_fr6_desk_host_exposes_merge_as_tool():
    from desk import build_desk_host, build_merge_tool

    merge_agent = build_merge_agent(CTX)
    host = build_desk_host(CTX, merge_agent)
    assert host.name == "Desk"
    assert any(getattr(t, "name", None) == "merge_findings" for t in host.tools)
    tool = build_merge_tool(merge_agent)
    assert tool.name == "merge_findings"


def test_fr6_pipeline_uses_as_tool_and_handoff():
    import desk.pipeline as pipeline_mod

    source = inspect.getsource(pipeline_mod)
    assert "build_desk_host" in source
    assert "handoffs=" in inspect.getsource(__import__("desk.agents", fromlist=["x"]))
    assert "Hand off to the Remediation agent" in source


def test_fr6_merge_dedupes_and_orders_by_severity():
    shared = Finding(file="a.py", line=1, severity="major", message="dup")
    sec = [
        Finding(file="a.py", line=10, severity="critical", message="rce"),
        shared,
    ]
    tst = [shared, Finding(file="b.py", line=2, severity="minor", message="no assert")]
    stl = [Finding(file="c.py", line=3, severity="major", message="naming")]

    report = merge_findings(sec, tst, stl)
    assert isinstance(report, MergedReport)
    severities = [f.severity for f in report.findings]
    assert severities == sorted(severities, key=lambda s: {"critical": 0, "major": 1, "minor": 2}[s])
    messages = [f.message for f in report.findings]
    assert messages.count("dup") == 1
    assert report.findings[0].severity == "critical"


def test_fr6_security_has_remediation_handoff():
    remediation = build_remediation_agent(CTX)
    security = build_security_reviewer(CTX, remediation=remediation)
    assert security.handoffs
    names = [h.agent_name for h in security.handoffs]
    assert "Remediation" in names
    tool_names = [h.tool_name for h in security.handoffs]
    assert any("remediation" in n.lower() for n in tool_names)


def test_fr6_handoff_is_agent_handoff_helper():
    remediation = build_remediation_agent(CTX)
    h = handoff(remediation)
    assert h.agent_name == "Remediation"
    security = build_security_reviewer(CTX, remediation=remediation)
    assert any(isinstance(x, type(h)) or getattr(x, "agent_name", None) == "Remediation" for x in security.handoffs)


def test_fr6_has_critical_finding_triggers_remediation_path():
    findings = [
        Finding(file="a.py", line=1, severity="critical", message="hardcoded key"),
        Finding(file="b.py", line=2, severity="minor", message="style"),
    ]
    assert has_critical_finding(findings) is True
    assert has_critical_finding(findings[1:]) is False


def test_fr6_remediation_agent_output_type():
    rem = build_remediation_agent(CTX)
    from desk import RemediationProposal

    assert rem.output_type is RemediationProposal


# --- FR-7: run-level model override ---

def test_fr7_run_config_model_override_without_agent_change():
    agent = build_security_reviewer(CTX)
    original = agent.model
    override = RunConfig(model="gpt-4o-mini")
    assert agent.model == original
    assert override.model == "gpt-4o-mini"


def test_fr7_run_reviewer_accepts_model_override():
    sig = inspect.signature(run_reviewer)
    assert "model_override" in sig.parameters


@pytest.mark.asyncio
async def test_fr7_model_override_passed_to_runner():
    captured = {}

    async def spy_runner(agent, inp, **kwargs):
        captured["run_config"] = kwargs.get("run_config")
        captured["agent_model"] = agent.model
        fake = type("R", (), {})()
        fake.final_output = []
        fake.final_output_as = lambda cls: []
        fake.last_agent = agent
        return fake

    agent = build_security_reviewer(CTX)
    await run_reviewer(agent, "diff", CTX, model_override="gpt-4o-mini", runner=spy_runner)
    assert captured["run_config"] is not None
    assert captured["run_config"].model == "gpt-4o-mini"
    assert captured["agent_model"] == agent.model


# --- FR-8: output guardrail secret refusal ---

def test_fr8_extract_secrets_from_diff():
    secrets = extract_secrets(SAMPLE_DIFF)
    assert any("sk-live" in s or "abcdef" in s for s in secrets)
    assert any("hunter2" in s for s in secrets)


def test_fr8_guardrail_trips_when_secret_in_output():
    secrets = extract_secrets(SAMPLE_DIFF)
    guardrail = build_secret_guardrail(secrets)
    assert isinstance(guardrail, OutputGuardrail)

    output = [
        Finding(
            file="src/app.py",
            line=3,
            severity="critical",
            message='found API_KEY = "sk-live-abcdef1234567890secret"',
        )
    ]
    result = guardrail.guardrail_function(None, None, output)
    assert isinstance(result, GuardrailFunctionOutput)
    assert result.tripwire_triggered is True


def test_fr8_guardrail_allows_clean_output():
    secrets = extract_secrets(SAMPLE_DIFF)
    guardrail = build_secret_guardrail(secrets)
    output = [
        Finding(file="src/app.py", line=3, severity="critical", message="hardcoded credential pattern")
    ]
    result = guardrail.guardrail_function(None, None, output)
    assert result.tripwire_triggered is False


def test_fr8_tripwire_raises_caught_exception_not_crash():
    secrets = extract_secrets(SAMPLE_DIFF)
    guardrail = build_secret_guardrail(secrets)
    output = [Finding(file="a.py", line=1, severity="critical", message="sk-live-abcdef1234567890secret")]
    fn_result = guardrail.guardrail_function(None, None, output)
    assert fn_result.tripwire_triggered

    agent = build_security_reviewer(CTX, secrets=secrets)
    og_result = OutputGuardrailResult(
        guardrail=guardrail,
        agent_output=output,
        agent=agent,
        output=fn_result,
    )
    exc = OutputGuardrailTripwireTriggered(og_result)
    assert isinstance(exc, OutputGuardrailTripwireTriggered)

    with pytest.raises(OutputGuardrailTripwireTriggered):
        raise exc


def test_fr8_reviewers_wired_with_secret_guardrail():
    secrets = extract_secrets(SAMPLE_DIFF)
    security = build_security_reviewer(CTX, secrets=secrets)
    assert security.output_guardrails
    names = [g.name for g in security.output_guardrails]
    assert "secret_leak_guardrail" in names


@pytest.mark.asyncio
async def test_fr8_runner_refusal_is_caught_without_crash():
    secrets = extract_secrets(SAMPLE_DIFF)
    guardrail = build_secret_guardrail(secrets)
    agent = build_security_reviewer(CTX, secrets=secrets)

    async def refusing_runner(agent, inp, **kwargs):
        output = [Finding(file="a.py", line=1, severity="critical", message="sk-live-abcdef1234567890secret")]
        fn_result = guardrail.guardrail_function(None, None, output)
        if fn_result.tripwire_triggered:
            og = OutputGuardrailResult(
                guardrail=guardrail, agent_output=output, agent=agent, output=fn_result
            )
            raise OutputGuardrailTripwireTriggered(og)
        fake = type("R", (), {})()
        fake.final_output = output
        fake.final_output_as = lambda cls: output
        fake.last_agent = agent
        return fake

    from desk.pipeline import _safe_run

    result = await _safe_run(agent, "diff", CTX, runner=refusing_runner)
    assert isinstance(result, str)
    assert result.startswith("refused:")


# --- FR-9: required tool choice, error handlers, turn ceilings ---

def test_fr9_force_ruleset_tool_choice_on_reviewers():
    security = build_security_reviewer(CTX)
    test = build_test_reviewer(CTX)
    style = build_style_reviewer(CTX)
    for a in (security, test, style):
        assert a.model_settings is not None
        assert a.model_settings.tool_choice == "read_ruleset"


def test_fr9_tool_has_failure_error_function():
    security = build_security_reviewer(CTX)
    tool = security.tools[0]
    assert isinstance(tool, FunctionTool)
    assert tool._failure_error_function is not None
    msg = tool._failure_error_function(None, RuntimeError("boom"))
    assert "error" in msg.lower()
    assert "boom" in msg


def test_fr9_missing_ruleset_file_returns_sentence_not_raise(tmp_path):
    import desk.agents as agents_mod
    from agents.tool_context import ToolContext

    ctx = ReviewContext(repo="r", language="python", ruleset_id="does-not-exist-ruleset")
    reviewer = build_reviewer(ctx, force_ruleset_tool=True)
    tool = reviewer.tools[0]
    assert tool.name == "read_ruleset"

    tool_ctx = ToolContext(
        context=None,
        tool_name=tool.name,
        tool_call_id="call_1",
        tool_arguments="{}",
    )
    result = asyncio.run(tool.on_invoke_tool(tool_ctx, "{}"))
    assert isinstance(result, str)
    assert "error" in result.lower()
    assert "does-not-exist-ruleset" in result
    assert "Continue" in result


async def _always_tool_runner(agent, inp, **kwargs):
    fake = type("R", (), {})()
    fake.final_output = []
    fake.final_output_as = lambda cls: []
    fake.last_agent = agent
    return fake


@pytest.mark.asyncio
async def test_fr9_max_turns_handler_reports_partial_not_raise():
    from desk.pipeline import make_max_turns_handler
    from agents import RunErrorData

    sink: dict = {}
    handler = make_max_turns_handler(sink)

    @dataclass
    class _DummyRunData:
        input: str = ""
        new_items: list = None
        history: list = None
        output: list = None
        raw_responses: list = None
        last_agent: object = None

    dummy = RunErrorData(
        input="x",
        new_items=[],
        history=[],
        output=[],
        raw_responses=[],
        last_agent=build_security_reviewer(CTX),
    )
    inp = type("I", (), {"run_data": dummy, "error": MaxTurnsExceeded("Max turns (1) exceeded"), "context": None})()
    result = handler(inp)
    assert sink["truncated"] is True
    assert result.final_output == []
    assert result.include_in_history is False


@pytest.mark.asyncio
async def test_fr9_run_reviewer_uses_error_handlers_on_max_turns():
    from desk.pipeline import make_max_turns_handler

    sink: dict = {}
    captured = {}

    async def max_turns_runner(agent, inp, **kwargs):
        captured.update(kwargs)
        handler = kwargs.get("error_handlers", {}).get("max_turns")
        assert handler is not None
        from agents import RunErrorData

        dummy = RunErrorData(
            input="x", new_items=[], history=[], output=[], raw_responses=[], last_agent=agent
        )
        handler_input = type("I", (), {"run_data": dummy, "error": None, "context": None})()
        handler_result = handler(handler_input)
        fake = type("R", (), {})()
        fake.final_output = handler_result.final_output
        fake.final_output_as = lambda cls: handler_result.final_output
        fake.last_agent = agent
        return fake

    agent = build_test_reviewer(CTX)
    result = await run_reviewer(
        agent, "diff", CTX, max_turns=1, runner=max_turns_runner, partial_sink=sink
    )
    assert sink["truncated"] is True
    assert result.final_output == []
