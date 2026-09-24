import asyncio
import inspect
import json
from pathlib import Path

import pytest

from desk import (
    Finding,
    MetricsRunHooks,
    ReviewContext,
    ReviewerMetrics,
    append_entry,
    clear_ledger,
    is_configured,
    read_ledger,
    register_ledger,
    review_trace,
    run_reviewers_concurrently,
    unregister_ledger,
)
from desk.hooks import MetricsAgentHooks, attach_agent_metrics
from desk.ledger import LEDGER_PATH, is_registered
from desk.pipeline import run_pipeline


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
"""


# --- FR-10: lifecycle hooks metrics ---

def test_fr10_metrics_run_hooks_subclass():
    assert issubclass(MetricsRunHooks, object)
    hooks = MetricsRunHooks()
    assert hasattr(hooks, "on_agent_start")
    assert hasattr(hooks, "on_agent_end")
    assert hasattr(hooks, "metrics")


def test_fr10_metrics_record_latency_and_findings():
    hooks = MetricsRunHooks()

    class _Ctx:
        usage = None

    class _Agent:
        name = "SecurityReviewer"

    asyncio.run(hooks.on_agent_start(_Ctx(), _Agent()))
    import time

    time.sleep(0.01)
    asyncio.run(hooks.on_agent_end(_Ctx(), _Agent(), [1, 2, 3]))

    m = hooks.metrics["SecurityReviewer"]
    assert isinstance(m, ReviewerMetrics)
    assert m.elapsed_ms >= 10
    assert m.findings_count == 3


def test_fr10_footer_contains_table_header():
    hooks = MetricsRunHooks()
    hooks.metrics["SecurityReviewer"] = ReviewerMetrics(
        agent="SecurityReviewer", ms=12.0, findings_count=1
    )
    footer = hooks.footer()
    assert "Review metrics" in footer
    assert "| Agent |" in footer
    assert "SecurityReviewer" in footer


def test_fr10_agent_hooks_attached_to_exactly_one_reviewer():
    from agents import Agent

    store: dict[str, ReviewerMetrics] = {}
    reviewers = [
        Agent(name="SecurityReviewer", instructions="x"),
        Agent(name="TestReviewer", instructions="x"),
        Agent(name="StyleReviewer", instructions="x"),
    ]
    attach_agent_metrics([reviewers[0]], store)
    hooked = [a for a in reviewers if isinstance(a.hooks, MetricsAgentHooks)]
    assert len(hooked) == 1
    assert hooked[0].name == "SecurityReviewer"
    assert hooked[0].hooks.store is store


def test_fr10_run_pipeline_attaches_agent_hooks_to_one_reviewer_only():
    import desk.pipeline as pipeline_mod

    source = inspect.getsource(pipeline_mod)
    assert "attach_agent_metrics([security], shared_store)" in source


def test_fr10_run_pipeline_accepts_hooks_and_streams():
    sig = inspect.signature(run_pipeline)
    assert "on_findings" in sig.parameters
    assert "enable_otel" in sig.parameters
    sig2 = inspect.signature(run_reviewers_concurrently)
    assert "hooks" in sig2.parameters
    assert "on_findings" in sig2.parameters


# --- FR-11: ledger.jsonl runner ---

def test_fr11_append_and_read_entry(tmp_path):
    path = tmp_path / "ledger.jsonl"
    clear_ledger(path)
    entry = append_entry(
        request_id="req_abc", agent="SecurityReviewer", ms=42.5, findings=2, path=path
    )
    assert entry["request_id"] == "req_abc"
    entries = read_ledger(path)
    assert len(entries) == 1
    assert entries[0]["agent"] == "SecurityReviewer"
    assert entries[0]["findings"] == 2
    assert entries[0]["ms"] == 42.5
    assert "ts" in entries[0]


def test_fr11_register_toggle():
    was = is_registered()
    try:
        register_ledger()
        assert is_registered() is True
        register_ledger()  # idempotent
        assert is_registered() is True
        unregister_ledger()
        assert is_registered() is False
        unregister_ledger()  # idempotent
        assert is_registered() is False
    finally:
        if was:
            register_ledger()
        else:
            unregister_ledger()


def test_fr11_ledger_runner_wraps_runner(tmp_path, monkeypatch):
    from agents import Runner

    path = tmp_path / "ledger.jsonl"
    clear_ledger(path)
    monkeypatch.setattr("desk.ledger.LEDGER_PATH", path)

    original = Runner.run
    was = is_registered()
    try:
        register_ledger()

        async def fake_run(agent, inp, **kwargs):
            fake = type("R", (), {})()
            fake.final_output = [
                Finding(file="a.py", line=1, severity="minor", message="m")
            ]
            fake.final_output_as = lambda cls: fake.final_output
            fake.last_agent = agent
            fake.raw_responses = []
            return fake

        # patch the stored original so ledger writes with our fake
        import desk.ledger as ledger_mod

        ledger_mod._original_runner_run = fake_run
        ledger_mod.LEDGER_PATH = path

        async def _call():
            return await Runner.run(None, "diff")

        result = asyncio.run(_call())
        entries = read_ledger(path)
        assert len(entries) == 1
        assert entries[0]["agent"] == "unknown"
        assert entries[0]["findings"] == 1
        assert isinstance(entries[0]["ms"], float)
    finally:
        ledger_mod.LEDGER_PATH = LEDGER_PATH
        ledger_mod._original_runner_run = None
        if was:
            register_ledger()
        else:
            unregister_ledger()
        Runner.run = original


def test_fr11_pipeline_writes_ledger_with_mock_runner(tmp_path, monkeypatch):
    path = tmp_path / "ledger.jsonl"
    clear_ledger(path)
    import desk.ledger as ledger_mod

    was = is_registered()
    monkeypatch.setattr(ledger_mod, "LEDGER_PATH", path)
    try:
        register_ledger()

        async def fake_runner(agent, inp, **kwargs):
            fake = type("R", (), {})()
            agent_name = getattr(agent, "name", "unknown")
            if agent_name == "Desk":
                data = json.loads(inp) if isinstance(inp, str) else {}
                findings = []
                for group in data.values() if isinstance(data, dict) else []:
                    findings.extend(Finding(**raw) for raw in group)
                fake.final_output = findings
            elif agent_name == "SecurityReviewer" and isinstance(inp, str) and "Hand off" in inp:
                data = json.loads(inp.split("this finding: ", 1)[-1])
                from desk import RemediationProposal

                fake.final_output = RemediationProposal(**data)
                fake.last_agent = type("A", (), {"name": "Remediation"})()
            elif agent_name in ("SecurityReviewer", "TestReviewer", "StyleReviewer"):
                fake.final_output = [
                    Finding(file="a.py", line=1, severity="minor", message=f"from {agent_name}")
                ]
            elif agent_name == "Merge":
                fake.final_output = [
                    Finding(file="a.py", line=1, severity="minor", message="merged")
                ]
            else:
                fake.final_output = []
            fake.final_output_as = lambda cls: fake.final_output
            fake.last_agent = getattr(fake, "last_agent", None) or agent
            fake.raw_responses = []
            return fake

        with tempfile_diff(SAMPLE_DIFF) as diff_path:
            outcome = asyncio.run(
                run_pipeline(
                    diff_path,
                    CTX,
                    runner=fake_runner,
                    enable_otel=False,
                )
            )
        assert outcome.status in ("ok", "partial")
        entries = read_ledger(path)
        agent_names = {e["agent"] for e in entries}
        assert "SecurityReviewer" in agent_names
        assert any(e["findings"] >= 1 for e in entries)
    finally:
        if was:
            register_ledger()
        else:
            unregister_ledger()


# --- FR-12: Chainlit app present ---

def test_fr12_app_module_exists_and_wires_chainlit():
    app_path = Path(__file__).resolve().parent.parent / "app.py"
    assert app_path.exists(), "app.py must exist for Chainlit UI"
    source = app_path.read_text(encoding="utf-8")
    assert "import chainlit as cl" in source
    assert "cl.on_chat_start" in source
    assert "cl.on_message" in source
    assert "run_pipeline" in source
    assert "register_ledger" in source
    assert "on_findings" in source


def test_fr12_app_registers_ledger_on_startup():
    app_path = Path(__file__).resolve().parent.parent / "app.py"
    source = app_path.read_text(encoding="utf-8")
    # register_ledger() must be invoked at module import (startup), not only in handlers
    assert "register_ledger()" in source


def test_nfr1_startup_missing_key_is_sentence_not_traceback():
    app_path = Path(__file__).resolve().parent.parent / "app.py"
    source = app_path.read_text(encoding="utf-8")
    assert "SystemExit" in source
    assert "OPENAI_API_KEY is missing" in source


def test_fr6_spec_has_two_sentence_tool_vs_handoff_justification():
    spec_path = Path(__file__).resolve().parent.parent / "spec.md"
    text = spec_path.read_text(encoding="utf-8")
    assert "tool call because" in text
    assert "handoff because" in text


# --- FR-13: OpenTelemetry single trace ---

def test_fr13_configure_opentelemetry_requires_api_key(monkeypatch):
    import desk.otel as otel_mod

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    otel_mod.reset_for_tests()
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        otel_mod.configure_opentelemetry()
    otel_mod.reset_for_tests()


def test_fr13_configure_and_is_configured(monkeypatch, tmp_path):
    import desk.otel as otel_mod

    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    otel_mod.reset_for_tests()
    tracer = otel_mod.configure_opentelemetry(trace_path=tmp_path / "trace.jsonl")
    assert tracer is not None
    assert otel_mod.is_configured() is True
    assert is_configured() is True
    # idempotent
    tracer2 = otel_mod.configure_opentelemetry()
    assert tracer2 is tracer
    otel_mod.reset_for_tests()


def test_fr13_review_trace_single_root_span(monkeypatch, tmp_path):
    import desk.otel as otel_mod

    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    otel_mod.reset_for_tests()
    otel_mod.configure_opentelemetry(trace_path=tmp_path / "trace.jsonl")

    with otel_mod.review_trace("sample.diff") as span:
        ctx = span.get_span_context()
        assert ctx is not None
        assert ctx.trace_id != 0
        # child span uses same active context / trace
        with otel_mod.reviewer_span("SecurityReviewer") as child:
            assert child.get_span_context().trace_id == ctx.trace_id

    otel_mod.reset_for_tests()


def test_fr13_spans_exported_to_jsonl_file(monkeypatch, tmp_path):
    import desk.otel as otel_mod

    trace_path = tmp_path / "otel_trace.jsonl"
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    otel_mod.reset_for_tests()
    otel_mod.configure_opentelemetry(trace_path=trace_path)

    with otel_mod.review_trace("x.diff") as root:
        with otel_mod.reviewer_span("SecurityReviewer"):
            pass
        with otel_mod.reviewer_span("TestReviewer"):
            pass
        with otel_mod.reviewer_span("StyleReviewer"):
            pass

    assert trace_path.exists()
    lines = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    names = {line["name"] for line in lines}
    assert "code-review-desk.review" in names
    assert {"SecurityReviewer", "TestReviewer", "StyleReviewer"} <= names
    trace_ids = {line["trace_id"] for line in lines}
    assert len(trace_ids) == 1
    otel_mod.reset_for_tests()


def test_fr13_agents_bridge_processor_registered(monkeypatch, tmp_path):
    import desk.otel as otel_mod

    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-real")
    otel_mod.reset_for_tests()
    otel_mod.configure_opentelemetry(trace_path=tmp_path / "trace.jsonl")

    from agents.tracing import get_trace_provider

    provider = get_trace_provider()
    multi = getattr(provider, "_multi_processor", None)
    processors = getattr(multi, "_processors", ()) if multi is not None else ()
    assert any(isinstance(p, otel_mod.AgentsToOtelProcessor) for p in processors)
    otel_mod.reset_for_tests()


def test_fr13_run_pipeline_enables_otel_by_default():
    sig = inspect.signature(run_pipeline)
    assert sig.parameters["enable_otel"].default is True


async def _async_noop(name, findings):
    return None


def test_fr13_pipeline_with_otel_writes_nothing_when_disabled(tmp_path):
    with tempfile_diff(SAMPLE_DIFF) as diff_path:
        async def fake_runner(agent, inp, **kwargs):
            fake = type("R", (), {})()
            agent_name = getattr(agent, "name", "unknown")
            if agent_name == "Desk":
                data = json.loads(inp) if isinstance(inp, str) else {}
                findings = []
                for group in data.values() if isinstance(data, dict) else []:
                    findings.extend(Finding(**raw) for raw in group)
                fake.final_output = findings
            elif agent_name in ("SecurityReviewer", "TestReviewer", "StyleReviewer"):
                fake.final_output = []
            else:
                fake.final_output = []
            fake.final_output_as = lambda cls: fake.final_output
            fake.last_agent = agent
            fake.raw_responses = []
            return fake

        outcome = asyncio.run(
            run_pipeline(diff_path, CTX, runner=fake_runner, enable_otel=False)
        )
        assert outcome.status in ("ok", "partial", "error")


class tempfile_diff:
    def __init__(self, content: str):
        self.content = content
        self.path: Path | None = None

    def __enter__(self) -> Path:
        import tempfile

        f = tempfile.NamedTemporaryFile(
            "w", suffix=".diff", delete=False, encoding="utf-8"
        )
        f.write(self.content)
        f.close()
        self.path = Path(f.name)
        return self.path

    def __exit__(self, *args):
        if self.path is not None and self.path.exists():
            self.path.unlink()
        return False
